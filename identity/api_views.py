from django.contrib.auth import authenticate
from django.db.models import Count

from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.generics import (
    ListAPIView, CreateAPIView, RetrieveAPIView, UpdateAPIView,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from config.permissions import IsAdmin
from .models import User, Role
from .serializers import (
    UserSerializer, UserDetailSerializer, UserCreateSerializer,
    UserUpdateSerializer, LoginSerializer, RegisterSerializer,
    ProfileUpdateSerializer,
)


# Brute-force koruma için endpoint-spesifik throttle scope'ları
class LoginRateThrottle(AnonRateThrottle):
    scope = 'login'


class RegisterRateThrottle(AnonRateThrottle):
    scope = 'register'


# Kimlik Doğrulama

# Kullanıcı girişi — JWT (access + refresh) ve legacy DRF token döndürür
@extend_schema(
    tags=['auth'],
    request=LoginSerializer,
    responses={
        200: inline_serializer(
            name='LoginResponse',
            fields={
                'access': serializers.CharField(),
                'refresh': serializers.CharField(),
                'token': serializers.CharField(),  # geriye dönük uyumluluk
                'user': UserSerializer(),
            },
        ),
        401: OpenApiResponse(description='Geçersiz kullanıcı adı veya şifre.'),
        403: OpenApiResponse(description='Hesap admin onayı bekliyor.'),
        429: OpenApiResponse(description='Çok fazla deneme — hız sınırı aşıldı.'),
    },
)
class LoginAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        username = serializer.validated_data['username']
        password = serializer.validated_data['password']
        user = authenticate(request, username=username, password=password)

        if user is not None:
            # JWT çifti üret (access kısa ömürlü, refresh uzun ömürlü)
            refresh = RefreshToken.for_user(user)
            # Legacy DRF token — geriye dönük uyumluluk için döndürülmeye devam
            legacy_token, _ = Token.objects.get_or_create(user=user)
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'token': legacy_token.key,
                'user': UserSerializer(user).data,
            })

        # Pasif hesap kontrolü — daha bilgilendirici hata mesajı
        try:
            existing = User.objects.get(username=username)
            if not existing.is_active:
                return Response(
                    {'detail': 'Hesabınız henüz admin tarafından onaylanmamıştır.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
        except User.DoesNotExist:
            pass

        return Response(
            {'detail': 'Geçersiz kullanıcı adı veya şifre.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )


# Kullanıcı çıkışı — Legacy token siler ve verilen refresh token'ı blacklist'e alır
@extend_schema(
    tags=['auth'],
    request=inline_serializer(
        name='LogoutRequest',
        fields={'refresh': serializers.CharField(required=False)},
    ),
    responses={200: OpenApiResponse(description='Çıkış yapıldı.')},
)
class LogoutAPIView(APIView):
    def post(self, request):
        # Legacy DRF token'ı sil
        Token.objects.filter(user=request.user).delete()

        # Refresh token verildiyse blacklist'e al (token rotation güvenliği)
        refresh = request.data.get('refresh')
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except Exception:
                # Geçersiz / blacklist edilemeyen token — sessizce yut
                pass

        return Response({'detail': 'Başarıyla çıkış yapıldı.'})


# Kayıt (Register) — Admin Onaylı

# Yeni kullanıcı kaydı — hesap pasif oluşturulur
@extend_schema(
    tags=['auth'],
    request=RegisterSerializer,
    responses={
        201: OpenApiResponse(description='Kayıt başarılı, admin onayı bekleniyor.'),
        429: OpenApiResponse(description='Çok fazla kayıt denemesi — hız sınırı aşıldı.'),
    },
)
class RegisterAPIView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [RegisterRateThrottle]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'detail': 'Kayıt başarılı! Hesabınız admin onayına gönderildi.'},
            status=status.HTTP_201_CREATED,
        )


# Profil

# Profil görüntüleme ve güncelleme
@extend_schema(tags=['auth'])
class ProfileAPIView(APIView):
    serializer_class = ProfileUpdateSerializer

    @extend_schema(responses={200: UserSerializer})
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    @extend_schema(request=ProfileUpdateSerializer, responses={200: UserSerializer})
    def put(self, request):
        serializer = ProfileUpdateSerializer(request.user, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)

    @extend_schema(request=ProfileUpdateSerializer, responses={200: UserSerializer})
    def patch(self, request):
        serializer = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)


# Profil silme (soft delete — hesabı deaktif eder ve token'ı siler)
@extend_schema(tags=['auth'], request=None, responses={200: OpenApiResponse(description='Hesap silindi.')})
class ProfileDeleteAPIView(APIView):
    def post(self, request):
        user = request.user
        user.is_active = False
        user.save(update_fields=['is_active'])
        Token.objects.filter(user=user).delete()
        return Response({'detail': 'Hesabınız başarıyla silindi.'})


# Admin: Kullanıcı Yönetimi

# Kullanıcı listesi — Sadece ADMIN
class UserListAPIView(ListAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]
    queryset = User.objects.all()

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        # Onay bekleyen kullanıcı sayısını ekle
        response.data['pending_count'] = User.objects.filter(is_active=False).count()
        return response


# Kullanıcı oluşturma — Sadece ADMIN
class UserCreateAPIView(CreateAPIView):
    serializer_class = UserCreateSerializer
    permission_classes = [IsAdmin]


# Kullanıcı detay — Sadece ADMIN
class UserDetailAPIView(RetrieveAPIView):
    serializer_class = UserDetailSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return User.objects.annotate(
            sent_tickets_count=Count('sent_tickets'),
            assigned_tickets_count=Count('assigned_tickets'),
        )


# Kullanıcı güncelleme — Sadece ADMIN
class UserUpdateAPIView(UpdateAPIView):
    serializer_class = UserUpdateSerializer
    permission_classes = [IsAdmin]
    queryset = User.objects.all()


# Kullanıcı silme (soft delete) — Sadece ADMIN
@extend_schema(tags=['users'], request=None, responses={200: OpenApiResponse(description='Kullanıcı deaktif edildi.')})
class UserDeleteAPIView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        user = User.objects.filter(pk=pk).first()
        if not user:
            return Response(
                {'detail': 'Kullanıcı bulunamadı.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Admin kendini silemez
        if user == request.user:
            return Response(
                {'detail': 'Kendi hesabınızı silemezsiniz.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_active = False
        user.save(update_fields=['is_active'])
        # Pasif hesabın oturumlarını / API token'ını da iptal et
        Token.objects.filter(user=user).delete()
        return Response({'detail': f'"{user.username}" kullanıcısı deaktif edildi.'})


# Kullanıcı onaylama — Sadece ADMIN (pasif hesabı aktif yapar)
@extend_schema(tags=['users'], request=None, responses={200: OpenApiResponse(description='Kullanıcı onaylandı.')})
class UserApproveAPIView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        user = User.objects.filter(pk=pk).first()
        if not user:
            return Response(
                {'detail': 'Kullanıcı bulunamadı.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        user.is_active = True
        user.save(update_fields=['is_active'])
        return Response({'detail': f'"{user.username}" kullanıcısı onaylandı ve aktif edildi.'})
