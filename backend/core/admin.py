from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import District, Region, User

# Tenant tables (memberships, audit log) are managed through the API, where the
# district context and row-level security apply; they are not in Django admin.


@admin.register(User)
class UserAdmin(BaseUserAdmin[User]):
    ordering = ["email"]
    list_display = ["email", "first_name", "last_name", "is_system_admin", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name")}),
        ("Access", {"fields": ("is_active", "is_system_admin", "is_staff", "is_superuser")}),
        ("Sign-in", {"fields": ("last_login", "failed_login_count", "locked_until")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin[Region]):
    list_display = ["name", "code"]


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin[District]):
    list_display = ["name", "code", "kind", "region", "is_active"]
    list_filter = ["region", "kind", "is_active"]
