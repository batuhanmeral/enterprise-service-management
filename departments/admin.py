from django.contrib import admin

from .models import Department, Category


# Departman sayfasında kategorileri inline olarak düzenle
class CategoryInline(admin.TabularInline):
    model = Category
    extra = 1
    verbose_name = 'Kategori'
    verbose_name_plural = 'Kategoriler'


# Departman modelini admin panelinde yönetmek için sınıf
@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):

    # Admin panelinde departman listesinde gösterilecek alanlar
    list_display = (
        'name',
        'description',
        'category_count',
        'personnel_count',
        'created_at',
    )

    # Admin panelinde departman listesinde filtreleme seçenekleri
    list_filter = (
        'created_at',
    )

    # Admin panelinde departman listesinde arama yapılacak alanlar
    search_fields = (
        'name',
        'description',
    )

    # Admin panelinde departman sayfasında kategorileri inline olarak düzenle
    inlines = [CategoryInline]

    # Admin panelinde sayfa başına gösterilecek departman sayısı
    list_per_page = 25

    # Admin panelinde departman detay sayfası alan grupları
    fieldsets = (
        (None, {
            'fields': ('name', 'description'),
        }),
    )

    # Departmana bağlı kategori sayısı
    @admin.display(description='Kategori Sayısı', ordering='name')
    def category_count(self, obj):
        return obj.categories.count()

    # Departmanda çalışan personel sayısı
    @admin.display(description='Personel Sayısı', ordering='name')
    def personnel_count(self, obj):
        return obj.personnel.count()


# Kategori modelini admin panelinde yönetmek için sınıf
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):

    # Admin panelinde kategori listesinde gösterilecek alanlar
    list_display = (
        'name',
        'department',
        'description',
    )

    # Admin panelinde kategori listesinde satır üzerinde düzenlenebilir alanlar
    list_editable = (
        'department',
    )

    # Admin panelinde kategori listesinde filtreleme seçenekleri
    list_filter = (
        'department',
    )

    # Admin panelinde kategori listesinde arama yapılacak alanlar
    search_fields = (
        'name',
        'department__name',
        'description',
    )

    # Admin panelinde sayfa başına gösterilecek kategori sayısı
    list_per_page = 25

    # Admin panelinde kategori detay sayfası alan grupları
    fieldsets = (
        (None, {
            'fields': ('department', 'name', 'description'),
        }),
    )

    # Toplu aksiyonlar
    actions = ['delete_selected']
