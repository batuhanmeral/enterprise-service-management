from django.contrib import admin

from .models import Notification


# Bildirim modelini admin panelinde yönetmek için sınıf
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):

    # Admin panelinde bildirim listesinde gösterilecek alanlar
    list_display = (
        'id',
        'recipient',
        'short_message',
        'ticket',
        'is_read',
        'created_at',
    )

    # Admin panelinde bildirim listesinde satır üzerinde düzenlenebilir alanlar
    list_editable = (
        'is_read',
    )

    # Admin panelinde bildirim listesinde filtreleme seçenekleri
    list_filter = (
        'is_read',
        'created_at',
    )

    # Admin panelinde bildirim listesinde arama yapılacak alanlar
    search_fields = (
        'message',
        'recipient__username',
        'recipient__first_name',
        'ticket__subject',
    )

    # Admin panelinde bildirim sayfasında salt okunur alanlar
    readonly_fields = (
        'created_at',
    )

    # Admin panelinde bildirim detay sayfası alan grupları
    fieldsets = (
        ('Bildirim Bilgileri', {
            'fields': ('recipient', 'ticket', 'message'),
        }),
        ('Durum', {
            'fields': ('is_read', 'created_at'),
        }),
    )

    # Admin panelinde bildirim listesinde ilişkili alanları önbelleğe al
    list_select_related = (
        'recipient',
        'ticket',
    )

    # Admin panelinde bildirim listesinde sayfa başına gösterilecek bildirim sayısı
    list_per_page = 30

    # Toplu aksiyonlar
    actions = ['mark_as_read', 'mark_as_unread']

    # Seçili bildirimleri okundu olarak işaretle
    @admin.action(description='Seçili bildirimleri "Okundu" olarak işaretle')
    def mark_as_read(self, request, queryset):
        count = queryset.update(is_read=True)
        self.message_user(request, f'{count} bildirim okundu olarak işaretlendi.')

    # Seçili bildirimleri okunmadı olarak işaretle
    @admin.action(description='Seçili bildirimleri "Okunmadı" olarak işaretle')
    def mark_as_unread(self, request, queryset):
        count = queryset.update(is_read=False)
        self.message_user(request, f'{count} bildirim okunmadı olarak işaretlendi.')

    # Bildirim mesajını kısaltılmış olarak göster
    @admin.display(description='Mesaj (Kısa)')
    def short_message(self, obj):
        return obj.message[:80] + '...' if len(obj.message) > 80 else obj.message
