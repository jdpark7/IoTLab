from django import forms

from .models import ALL_COMPONENTS, COMPONENT_CHOICES
from .services import parse_roster


class EnrollForm(forms.Form):
    roster = forms.CharField(
        label="Students",
        widget=forms.Textarea(attrs={"rows": 10, "placeholder": "a10301,Budi Santoso,budi@example.com\na10302,Siti Rahma\na10303"}),
        help_text="One per line: username[,full name[,email]]. CSV or tab-separated (pasted from a spreadsheet) works.",
        required=False,
    )
    csv_file = forms.FileField(label="…or upload CSV", required=False)
    cohort = forms.CharField(max_length=64, required=False, help_text="e.g. IoT 2026-2")
    components = forms.MultipleChoiceField(
        choices=COMPONENT_CHOICES, initial=ALL_COMPONENTS, widget=forms.CheckboxSelectMultiple,
    )

    def clean(self):
        data = super().clean()
        text = data.get("roster") or ""
        f = data.get("csv_file")
        if f:
            if f.size > 1_000_000:
                raise forms.ValidationError("CSV file is too large.")
            text += "\n" + f.read().decode("utf-8-sig", errors="replace")
        rows, errors = parse_roster(text)
        if errors:
            raise forms.ValidationError(errors)
        if not rows:
            raise forms.ValidationError("Enter at least one username.")
        data["rows"] = rows
        return data


class ComponentsForm(forms.Form):
    components = forms.MultipleChoiceField(choices=COMPONENT_CHOICES, widget=forms.CheckboxSelectMultiple)
    cohort = forms.CharField(max_length=64, required=False)
    full_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)


class ConfirmRemoveForm(forms.Form):
    purge = forms.BooleanField(
        required=False, label="Also delete the Linux account, home directory, /srv data and database",
    )
    confirm = forms.CharField(help_text="Type the username to confirm")

    def __init__(self, *args, username=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.username = username

    def clean_confirm(self):
        v = self.cleaned_data["confirm"].strip()
        if v != self.username:
            raise forms.ValidationError("Username does not match.")
        return v
