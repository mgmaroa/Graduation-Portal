from django.conf import settings
from django.db import models

from .utils import normalize_admission_no


class Graduand(models.Model):
    """A student on the registrar's graduation list."""

    admission_no = models.CharField(
        max_length=30, unique=True,
        help_text="Stored in normalized form (uppercase, no stray spaces).",
    )
    student_name = models.CharField(max_length=150)
    course = models.CharField(max_length=200)
    school = models.CharField("School / department", max_length=200)
    graduation_date = models.DateField()
    is_dummy = models.BooleanField(
        default=False,
        help_text="True for demo records. They can be cleared before the real list is loaded.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["admission_no"]
        verbose_name = "graduand"
        verbose_name_plural = "graduands"

    def save(self, *args, **kwargs):
        self.admission_no = normalize_admission_no(self.admission_no)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.admission_no} - {self.student_name}"


class UploadLog(models.Model):
    """Audit trail: who uploaded which list, and when."""

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="graduation_uploads",
    )
    filename = models.CharField(max_length=255)
    records_total = models.PositiveIntegerField(default=0)
    records_added = models.PositiveIntegerField(default=0)
    records_updated = models.PositiveIntegerField(default=0)
    records_rejected = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.filename} ({self.uploaded_at:%Y-%m-%d %H:%M})"


class LookupAttempt(models.Model):
    """
    One row per student lookup. Feeds rate limiting and lets ICT
    spot suspicious activity (e.g. one IP trying many numbers).
    """

    ip_address = models.GenericIPAddressField()
    searched_value = models.CharField(max_length=50, blank=True)
    found = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["ip_address", "created_at"]),
        ]

    def __str__(self):
        status = "found" if self.found else "not found"
        return f"{self.ip_address} -> {self.searched_value} ({status})"