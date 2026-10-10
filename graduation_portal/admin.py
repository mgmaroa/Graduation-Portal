from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from .forms import GraduandAdminForm, UploadForm
from .importer import UploadError, apply_import, build_plan, parse_upload
from .models import Graduand, LookupAttempt, UploadLog

SESSION_KEY = "graduation_pending_import"
PREVIEW_LIMIT = 50


@admin.register(Graduand)
class GraduandAdmin(admin.ModelAdmin):
    form = GraduandAdminForm
    change_list_template = "admin/graduation_portal/graduand/change_list.html"
    list_display = ("admission_no", "student_name", "course", "school",
                    "graduation_date", "manually_edited", "is_dummy")
    list_filter = ("is_dummy", "manually_edited", "school", "graduation_date")
    search_fields = ("admission_no", "student_name", "course", "school")
    readonly_fields = ("is_dummy", "manually_edited", "created_at", "updated_at")

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial.setdefault("graduation_date", settings.GRADUATION_DATE)
        return initial

    def save_model(self, request, obj, form, change):
        # Anything entered or corrected here is protected from later list uploads.
        # (Django's built-in History button records who changed what, and when.)
        if not change or form.changed_data:
            obj.manually_edited = True
        super().save_model(request, obj, form, change)

    # ---- custom pages: upload, preview, confirm, template ----------------
    def get_urls(self):
        wrap = self.admin_site.admin_view
        custom = [
            path("upload/", wrap(self.upload_view), name="graduation_portal_graduand_upload"),
            path("upload/confirm/", wrap(self.confirm_view), name="graduation_portal_graduand_upload_confirm"),
            path("upload/template.csv", wrap(self.template_view), name="graduation_portal_graduand_template"),
        ]
        return custom + super().get_urls()

    def _check(self, request):
        if not (self.has_add_permission(request) and self.has_change_permission(request)):
            raise PermissionDenied

    def _context(self, request, title, **extra):
        return {**self.admin_site.each_context(request), "title": title,
                "opts": self.model._meta, **extra}

    def upload_view(self, request):
        self._check(request)
        form = UploadForm()

        if request.method == "POST":
            form = UploadForm(request.POST, request.FILES)
            if form.is_valid():
                upload = form.cleaned_data["file"]
                try:
                    parsed = parse_upload(upload)
                except UploadError as exc:
                    form.add_error("file", str(exc))
                else:
                    opts = {"overwrite_manual": form.cleaned_data["overwrite_manual"],
                            "remove_dummy": form.cleaned_data["remove_dummy"]}
                    plan = build_plan(parsed.rows, **opts)
                    request.session[SESSION_KEY] = {
                        "filename": upload.name, "rows": parsed.rows,
                        "rejected": parsed.rejected, "total": parsed.total, **opts,
                    }
                    return TemplateResponse(request, "admin/graduation_portal/graduand/upload_preview.html",
                        self._context(
                            request, "Check the list before applying it",
                            filename=upload.name, parsed=parsed, plan=plan, **opts,
                            updates=plan.update[:PREVIEW_LIMIT],
                            skipped=plan.skipped_manual[:PREVIEW_LIMIT],
                            rejected=parsed.rejected[:PREVIEW_LIMIT],
                            extra_updates=max(0, len(plan.update) - PREVIEW_LIMIT),
                            extra_skipped=max(0, len(plan.skipped_manual) - PREVIEW_LIMIT),
                            extra_rejected=max(0, len(parsed.rejected) - PREVIEW_LIMIT),
                        ))

        real = Graduand.objects.filter(is_dummy=False)
        return TemplateResponse(request, "admin/graduation_portal/graduand/upload.html", self._context(
            request, "Upload graduation list", form=form, default_date=settings.GRADUATION_DATE,
            real_count=real.count(),
            dummy_count=Graduand.objects.filter(is_dummy=True).count(),
            edited_count=real.filter(manually_edited=True).count(),
        ))

    def confirm_view(self, request):
        self._check(request)
        if request.method != "POST":
            return redirect("admin:graduation_portal_graduand_upload")

        pending = request.session.pop(SESSION_KEY, None)
        if not pending:
            messages.error(request, "That upload has expired or was already applied. Please upload the file again.")
            return redirect("admin:graduation_portal_graduand_upload")

        log = apply_import(
            pending["rows"], [tuple(r) for r in pending["rejected"]], pending["total"],
            filename=pending["filename"], user=request.user,
            overwrite_manual=pending["overwrite_manual"], remove_dummy=pending["remove_dummy"],
        )
        parts = [f"{log.records_added} added", f"{log.records_updated} updated"]
        if log.records_skipped:
            parts.append(f"{log.records_skipped} left alone (edited by hand)")
        if log.records_rejected:
            parts.append(f"{log.records_rejected} rejected")
        if log.dummy_removed:
            parts.append(f"{log.dummy_removed} demo records removed")
        messages.success(request, f"Upload applied: {', '.join(parts)}.")
        return redirect("admin:graduation_portal_graduand_changelist")

    def template_view(self, request):
        self._check(request)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="graduation_list_template.csv"'
        response.write("admission_no,student_name,course,school,graduation_date\r\n")
        return response


@admin.register(UploadLog)
class UploadLogAdmin(admin.ModelAdmin):
    list_display = ("uploaded_at", "filename", "uploaded_by", "records_total", "records_added",
                    "records_updated", "records_skipped", "records_rejected", "dummy_removed")
    readonly_fields = [f.name for f in UploadLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
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