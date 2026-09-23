from django.contrib import admin

from .models import CoordinateSystem


@admin.register(CoordinateSystem)
class CoordinateSystemAdmin(admin.ModelAdmin[CoordinateSystem]):
    list_display = ["code", "name", "units", "is_builtin", "is_active"]
    list_filter = ["is_builtin", "is_active", "kind"]
    search_fields = ["code", "name"]
    readonly_fields = ["srid", "wkt", "proj4"]
