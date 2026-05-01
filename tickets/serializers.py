from rest_framework import serializers

from identity.serializers import UserShortSerializer
from .models import Ticket, TicketComment, TicketHistory, TicketAttachment, Tag


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
            'resolution_note',
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
    attachments = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        write_only=True,
    )

    class Meta:
        model = Ticket
        fields = ['subject', 'message', 'department', 'category', 'priority', 'tags', 'attachments']

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
    attachments = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        write_only=True,
    )

    class Meta:
        model = Ticket
        fields = ['subject', 'message', 'department', 'category', 'priority', 'tags', 'attachments']

    def validate(self, attrs):
        _validate_category_department(attrs, instance=self.instance)
        return attrs

    def update(self, instance, validated_data):
        files = validated_data.pop('attachments', [])
        ticket = super().update(instance, validated_data)
        for f in files:
            TicketAttachment.objects.create(ticket=ticket, file=f, uploaded_by=ticket.sender)
        return ticket


# Bilet kapatma serializer'ı
class TicketCloseSerializer(serializers.Serializer):
    resolution_note = serializers.CharField(required=False, default='', allow_blank=True)


# Bilet transfer serializer'ı
class TicketTransferSerializer(serializers.Serializer):
    department = serializers.IntegerField()
    category = serializers.IntegerField(required=False, allow_null=True, default=None)


# Bilet yorum serializer'ı
class TicketCommentSerializer(serializers.ModelSerializer):
    author = UserShortSerializer(read_only=True)

    class Meta:
        model = TicketComment
        fields = ['id', 'author', 'content', 'created_at']
        read_only_fields = ['id', 'author', 'created_at']
