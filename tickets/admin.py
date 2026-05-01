from django.contrib import admin

from .models import Ticket, Status, TicketHistory, TicketComment, TicketAttachment, Tag


# Etiket — admin'den oluşturulup yönetilebilir
@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'color', 'created_at')
    search_fields = ('name',)
    ordering = ('name',)


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

    # M2M alanları için yatay seçici
    filter_horizontal = ('tags',)

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


# Bilet geçmişi (audit log) — sadece okunur, değiştirilemez
@admin.register(TicketHistory)
class TicketHistoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'ticket', 'actor', 'action', 'created_at')
    list_filter = ('created_at', 'actor')
    search_fields = ('action', 'ticket__subject', 'actor__username')
    list_select_related = ('ticket', 'actor')
    date_hierarchy = 'created_at'
    list_per_page = 50
    ordering = ('-created_at',)
    # Audit log immutability — admin'den de değiştirilemez
    readonly_fields = ('ticket', 'actor', 'action', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# Bilet ekleri — admin'den görüntülenebilir
@admin.register(TicketAttachment)
class TicketAttachmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'ticket', 'filename', 'uploaded_by', 'uploaded_at')
    list_filter = ('uploaded_at',)
    search_fields = ('file', 'ticket__subject', 'uploaded_by__username')
    list_select_related = ('ticket', 'uploaded_by')
    readonly_fields = ('uploaded_at',)


# Bilet yorumları — admin'den görüntülenebilir
@admin.register(TicketComment)
class TicketCommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'ticket', 'author', 'short_content', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('content', 'ticket__subject', 'author__username')
    list_select_related = ('ticket', 'author')
    date_hierarchy = 'created_at'
    list_per_page = 50
    ordering = ('-created_at',)
    readonly_fields = ('ticket', 'author', 'created_at')

    @admin.display(description='Yorum')
    def short_content(self, obj):
        return obj.content[:60] + ('…' if len(obj.content) > 60 else '')
