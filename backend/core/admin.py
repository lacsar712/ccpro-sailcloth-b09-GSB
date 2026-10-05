from django.contrib import admin

from .models import ClothRoll, DipRun, Loft, WeightAuditLog


@admin.register(WeightAuditLog)
class WeightAuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "roll",
        "old_value",
        "new_value",
        "changed_by_username",
        "source",
        "changed_at",
    )
    list_filter = ("source", "changed_at")
    search_fields = ("roll__roll_code", "changed_by_username")
    readonly_fields = (
        "roll",
        "old_value",
        "new_value",
        "changed_by",
        "changed_by_username",
        "source",
        "changed_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Loft)
admin.site.register(ClothRoll)
admin.site.register(DipRun)
