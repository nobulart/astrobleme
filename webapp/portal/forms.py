import json

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import CandidateSubmission


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")


class CandidateForm(forms.ModelForm):
    EVIDENCE_CHOICES = [
        ("gravity", "Gravity"), ("magnetic", "Magnetic"), ("geology", "Detailed geology"),
        ("seismic", "Seismic"), ("field", "Field observation"),
        ("petrography", "Petrography"), ("geochemistry", "Geochemistry"),
    ]
    independent_evidence = forms.MultipleChoiceField(choices=EVIDENCE_CHOICES, required=False, widget=forms.CheckboxSelectMultiple)
    geometry_text = forms.CharField(required=False, widget=forms.HiddenInput)
    terms_confirmed = forms.BooleanField(label="I understand that morphology and screening scores do not confirm an impact origin.")

    class Meta:
        model = CandidateSubmission
        exclude = ("created_by", "geometry", "intake_score", "followup_score", "followup_status", "followup_metrics", "followup_method_version", "baseline_passed", "baseline_checks", "status", "moderator_notes", "moderated_by", "moderated_at")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "endogenic_alternative": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_geometry_text(self):
        raw = self.cleaned_data.get("geometry_text")
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("The map geometry is not valid GeoJSON.") from exc
        if value.get("type") not in {"LineString", "MultiLineString", "Polygon"}:
            raise forms.ValidationError("Use a line or polygon geometry for the observed trace.")
        return value
