from django.contrib import admin

from .models import Ticket, Status


# Talep modelini admin panelinde yönetmek için sınıf
@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):

    # Admin panelinde talep listesinde gösterilecek alanlar
    list_display = (
        'id',
        'subject',
        'status',
        'sender',
        'assigned_to',
        'department',
        'category',
        'created_at',
        'closed_at',
    )

    # Admin panelinde talep listesinde satır üzerinde düzenlenebilir alanlar
    list_editable = (
        'status',
        'assigned_to',
    )

    # Admin panelinde talep listesinde filtreleme seçenekleri
    list_filter = (
        'status',
        'department',
        'category',
        'created_at',
        'closed_at',
    )

    # Admin panelinde talep listesinde arama yapılacak alanlar
    search_fields = (
        'subject',
        'message',
        'resolution_note',
        'sender__username',
        'sender__first_name',
        'sender__last_name',
        'assigned_to__username',
    )

    # Admin panelinde talep sayfasında salt okunur alanlar
    readonly_fields = (
        'created_at',
        'updated_at',
        'closed_at',
    )

    # Admin panelinde talep sayfasında alan grupları
    fieldsets = (
        ('Talep Bilgileri', {
            'fields': ('subject', 'message', 'attachment'),
        }),
        ('Durum ve Atama', {
            'fields': ('status', 'sender', 'assigned_to', 'department', 'category'),
        }),
        ('Çözüm', {
            'fields': ('resolution_note',),
            'classes': ('collapse',),
        }),
        ('Zaman Bilgileri', {
            'fields': ('created_at', 'updated_at', 'closed_at'),
        }),
    )

    # Admin panelinde talep listesinde ilişkili alanları önbelleğe al
    list_select_related = (
        'sender',
        'assigned_to',
        'department',
        'category',
    )

    # Admin panelinde talep listesinde sayfa başına gösterilecek talep sayısı
    list_per_page = 25

    # Admin panelinde talep listesinde tarih hiyerarşisi
    date_hierarchy = 'created_at'

    # Toplu aksiyonlar
    actions = ['mark_open', 'mark_in_progress', 'mark_closed', 'clear_assignment']

    # Seçili biletleri Açık durumuna getir
    @admin.action(description='Seçili biletleri "Açık" durumuna getir')
    def mark_open(self, request, queryset):
        count = queryset.update(status=Status.OPEN, assigned_to=None)
        self.message_user(request, f'{count} bilet "Açık" durumuna getirildi.')

    # Seçili biletleri İşlemde durumuna getir
    @admin.action(description='Seçili biletleri "İşlemde" durumuna getir')
    def mark_in_progress(self, request, queryset):
        count = queryset.update(status=Status.IN_PROGRESS)
        self.message_user(request, f'{count} bilet "İşlemde" durumuna getirildi.')

    # Seçili biletleri Kapalı durumuna getir
    @admin.action(description='Seçili biletleri "Kapalı" durumuna getir')
    def mark_closed(self, request, queryset):
        from django.utils import timezone
        count = queryset.update(status=Status.CLOSED, closed_at=timezone.now())
        self.message_user(request, f'{count} bilet kapatıldı.')

    # Seçili biletlerin atamasını sıfırla
    @admin.action(description='Seçili biletlerin personel atamasını kaldır')
    def clear_assignment(self, request, queryset):
        count = queryset.update(assigned_to=None)
        self.message_user(request, f'{count} biletin personel ataması kaldırıldı.')
