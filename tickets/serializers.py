from rest_framework import serializers

from identity.models import User
from .models import Ticket, TicketComment, TicketHistory, TicketAttachment, Tag, Status as TicketStatus



# Kısa kullanıcı referansı — bilet nested alanlarında kullanılır
class UserShortSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'full_name']

    def get_full_name(self, obj) -> str:
        return obj.get_full_name() or obj.username


# Etiket serializer'ı
class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'color']


# Ek (file attachment) serializer'ı
class TicketAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by = UserShortSerializer(read_only=True)
    filename = serializers.CharField(read_only=True)
    file = serializers.FileField()

    class Meta:
        model = TicketAttachment
        fields = ['id', 'file', 'filename', 'uploaded_by', 'uploaded_at']
        read_only_fields = ['id', 'filename', 'uploaded_by', 'uploaded_at']


# Bilet geçmişi (audit log) serializer'ı
class TicketHistorySerializer(serializers.ModelSerializer):
    actor = UserShortSerializer(read_only=True)

    class Meta:
        model = TicketHistory
        fields = ['id', 'actor', 'action', 'created_at']


# Bilet listesi serializer'ı — kısa bilgiler
class TicketListSerializer(serializers.ModelSerializer):
    sender = UserShortSerializer(read_only=True)
    assigned_to = UserShortSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True, default=None)
    category_name = serializers.CharField(source='category.name', read_only=True, default=None)
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Ticket
        fields = [
            'id', 'subject', 'status', 'status_display',
            'priority', 'priority_display',
            'department', 'department_name',
            'category', 'category_name',
            'sender', 'assigned_to', 'tags', 'created_at',
        ]


# Bilet detay serializer'ı — tüm alanlar + audit log
class TicketDetailSerializer(serializers.ModelSerializer):
    sender = UserShortSerializer(read_only=True)
    assigned_to = UserShortSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True, default=None)
    category_name = serializers.CharField(source='category.name', read_only=True, default=None)
    history = TicketHistorySerializer(many=True, read_only=True)
    attachments = TicketAttachmentSerializer(many=True, read_only=True)
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Ticket
        fields = [
            'id', 'subject', 'message', 'attachments', 'tags',
            'status', 'status_display', 'priority', 'priority_display',
            'resolution_note', 'resolution_confirmed',
            'resolved_at', 'reopen_count', 'rejection_reason',
            'escalated_at', 'csat_rating',
            'department', 'department_name', 'category', 'category_name',
            'sender', 'assigned_to',
            'created_at', 'updated_at', 'closed_at',
            'history',
        ]


# Kategori-departman tutarlılığı; her iki create/update için ortak
def _validate_category_department(attrs, instance=None):
    department = attrs.get('department') or (instance.department if instance else None)
    category = attrs.get('category') or (instance.category if instance else None)
    if category and department and category.department_id != department.pk:
        raise serializers.ValidationError({
            'category': 'Seçilen kategori bu departmana ait değil.',
        })


# Bilet oluşturma serializer'ı — çoklu dosya yüklemesi destekler
class TicketCreateSerializer(serializers.ModelSerializer):
    sender = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)
    attachments = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        write_only=True,
    )

    class Meta:
        model = Ticket
        fields = ['subject', 'message', 'department', 'category', 'priority', 'tags', 'attachments', 'sender']

    def validate(self, attrs):
        _validate_category_department(attrs)
        return attrs

    def create(self, validated_data):
        files = validated_data.pop('attachments', [])
        ticket = super().create(validated_data)
        for f in files:
            TicketAttachment.objects.create(ticket=ticket, file=f, uploaded_by=ticket.sender)
        return ticket


# Bilet güncelleme serializer'ı — yeni dosyalar mevcut listeye eklenir
class TicketUpdateSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=TicketStatus.choices, required=False)
    assigned_to = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    attachments = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        write_only=True,
    )

    class Meta:
        model = Ticket
        fields = ['subject', 'message', 'department', 'category', 'priority', 'tags', 'attachments', 'status', 'assigned_to']

    def validate(self, attrs):
        _validate_category_department(attrs, instance=self.instance)
        return attrs

    def update(self, instance, validated_data):
        files = validated_data.pop('attachments', [])
        ticket = super().update(instance, validated_data)
        for f in files:
            TicketAttachment.objects.create(ticket=ticket, file=f, uploaded_by=ticket.sender)
        return ticket


# Bilet çözüldü olarak işaretleme — resolution_note zorunlu
class TicketResolveSerializer(serializers.Serializer):
    resolution_note = serializers.CharField(required=True, allow_blank=False, max_length=1000)


# Çözüm reddi — gerekçe zorunlu
class TicketRejectResolutionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True, allow_blank=False, max_length=1000)


# CSAT — 1-5 puan
class TicketCsatSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)


# Bilet transfer serializer'ı
class TicketTransferSerializer(serializers.Serializer):
    department = serializers.IntegerField()
    category = serializers.IntegerField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        from departments.models import Category
        cat_id = attrs.get('category')
        dept_id = attrs.get('department')
        if cat_id and dept_id:
            if not Category.objects.filter(pk=cat_id, department_id=dept_id).exists():
                raise serializers.ValidationError({
                    'category': 'Seçilen kategori bu departmana ait değil.',
                })
        return attrs


# Bilet yorum serializer'ı
class TicketCommentSerializer(serializers.ModelSerializer):
    author = UserShortSerializer(read_only=True)

    class Meta:
        model = TicketComment
        fields = ['id', 'author', 'content', 'attachment', 'created_at']
        read_only_fields = ['id', 'author', 'created_at']

    def validate(self, attrs):
        if not attrs.get('content') and not attrs.get('attachment'):
            raise serializers.ValidationError(
                'Mesaj veya dosya eklerinden en az birini gönderin.'
            )
        return attrs
