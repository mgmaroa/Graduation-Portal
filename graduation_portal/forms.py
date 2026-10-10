import re

from captcha.fields import CaptchaField
from django import forms
from django.conf import settings

from .models import Graduand
from .utils import normalize_admission_no


class LookupForm(forms.Form):
    admission_no = forms.CharField(
        label="Admission number",
        max_length=20,
        widget=forms.TextInput(attrs={
            "inputmode": "numeric",
            "autocomplete": "off",
            "autofocus": True,
            "placeholder": "e.g. 11300",
        }),
    )
    captcha = CaptchaField(
        label="Security check",
        error_messages={"invalid": "Wrong answer. Solve the new sum and try again."},
    )

    def clean_admission_no(self):
        value = normalize_admission_no(self.cleaned_data["admission_no"])
        if not re.fullmatch(settings.ADMISSION_NO_PATTERN, value):
            raise forms.ValidationError(
                "Enter your admission number using digits only (4 to 6 digits)."
            )
        return value


class UploadForm(forms.Form):
    """ICT chief uploads the registrar's list."""

    file = forms.FileField(
        label="Graduation list",
        help_text="CSV or Excel (.xlsx), up to 5 MB.",
    )
    remove_dummy = forms.BooleanField(
        label="Remove demo records first",
        required=False, initial=True,
        help_text="Demo records could share an admission number with a real student, "
                  "so they are cleared when the real list goes in.",
    )
    overwrite_manual = forms.BooleanField(
        label="Overwrite records that were edited by hand",
        required=False,
        help_text="Leave unticked to protect corrections you made in the admin.",
    )


class GraduandAdminForm(forms.ModelForm):
    """Same checks as the upload, so hand-entered data is as clean as uploaded data."""

    class Meta:
        model = Graduand
        fields = "__all__"

    def clean_admission_no(self):
        value = normalize_admission_no(self.cleaned_data["admission_no"])
        if not re.fullmatch(settings.ADMISSION_NO_PATTERN, value):
            raise forms.ValidationError("Use digits only (4 to 6 digits).")
        return value

    def _tidy(self, name):
        return " ".join(self.cleaned_data[name].split())

    def clean_student_name(self):
        return self._tidy("student_name")

    def clean_course(self):
        return self._tidy("course")

    def clean_school(self):
        return self._tidy("school")