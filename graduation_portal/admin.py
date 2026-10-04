from django.contrib import admin

from .models import Graduand, LookupAttempt, UploadLog


@admin.register(Graduand)
class GraduandAdmin(admin.ModelAdmin):
    list_display = ("admission_no", "student_name", "course", "school",
                    "graduation_date", "is_dummy")
    list_filter = ("is_dummy", "school", "graduation_date")
    search_fields = ("admission_no", "student_name", "course")


@admin.register(UploadLog)
class UploadLogAdmin(admin.ModelAdmin):
    list_display = ("filename", "uploaded_by", "records_total", "records_added",
                    "records_updated", "records_rejected", "uploaded_at")
    readonly_fields = [f.name for f in UploadLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(LookupAttempt)
class LookupAttemptAdmin(admin.ModelAdmin):
    list_display = ("created_at", "ip_address", "searched_value", "found")
    list_filter = ("found",)
    search_fields = ("ip_address", "searched_value")
    readonly_fields = [f.name for f in LookupAttempt._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False