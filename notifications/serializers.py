from rest_framework import serializers

from .models import Notification


# Bildirim listesi serializer'ı
class NotificationSerializer(serializers.ModelSerializer):
    ticket_subject = serializers.CharField(source='ticket.subject', read_only=True, default=None)

    class Meta:
        model = Notification
        fields = ['id', 'message', 'is_read', 'created_at', 'ticket', 'ticket_subject']


# Bildirim detay serializer'ı
class NotificationDetailSerializer(serializers.ModelSerializer):
    ticket_subject = serializers.CharField(source='ticket.subject', read_only=True, default=None)

    class Meta:
        model = Notification
        fields = ['id', 'message', 'is_read', 'created_at', 'ticket', 'ticket_subject']
