from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User

from tenants.models import Tenant, TenantMembership, TenantRole


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "timezone", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "role", "created_at")
    list_filter = ("role", "tenant")
    search_fields = ("user__username", "tenant__name", "tenant__slug")
    autocomplete_fields = ("user", "tenant")


class TenantMembershipCreateInline(admin.TabularInline):
    model = TenantMembership
    extra = 1
    max_num = 1
    fields = ("tenant", "role")
    verbose_name = "首个租户管理员"
    verbose_name_plural = "首个租户管理员"

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.form.base_fields["role"].initial = TenantRole.TENANT_ADMIN
        return formset


class PlatformUserAdmin(DjangoUserAdmin):
    inlines = (*DjangoUserAdmin.inlines, TenantMembershipCreateInline)


admin.site.unregister(User)
admin.site.register(User, PlatformUserAdmin)
