import re

from captcha.fields import CaptchaField
from django import forms
from django.conf import settings

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