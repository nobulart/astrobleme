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
    FIELD_LABELS = {
        "title": "Candidate title",
        "description": "Review rationale",
        "longitude": "Estimated centre longitude",
        "latitude": "Estimated centre latitude",
        "diameter_km": "Estimated characteristic diameter",
        "source_title": "Primary source title",
        "source_uri": "Primary source link",
        "source_resolution": "Source resolution or map scale",
        "observed_feature": "Observed feature",
        "endogenic_alternative": "Best non-impact alternative",
        "independent_evidence": "Independent supporting evidence",
        "original_trace_available": "Original trace preserved",
    }
    FIELD_HELP_TEXT = {
        "title": (
            "Use a neutral, location- or source-based name for the candidate. Avoid confirmed terms such as "
            "\"impact crater\" unless the record already has diagnostic shock, meteoritic, or projectile evidence."
        ),
        "description": (
            "Describe exactly what is visible and why it is worth review: annular or arcuate continuity, radial "
            "patterns, relief, gravity/magnetic/geologic context, and the data source used. Keep claims provisional; "
            "morphology and automated scores are screening evidence, not confirmation."
        ),
        "longitude": (
            "Enter the WGS84 decimal longitude for the estimated centre of the candidate geometry. East is positive "
            "and west is negative. This is a review anchor, not a statement that a crater centre has been proven."
        ),
        "latitude": (
            "Enter the WGS84 decimal latitude for the estimated centre of the candidate geometry. North is positive "
            "and south is negative. Use the centre implied by the visible trace or the mapped anomaly."
        ),
        "diameter_km": (
            "Estimate the characteristic ring, rim, basin, or anomaly scale in kilometres. This is not a final or "
            "transient crater diameter; it only defines the scale used for screening, duplicate checks, and follow-up."
        ),
        "source_title": (
            "Name the source that supports the observation, such as Esri World Imagery, GEBCO elevation, WGM gravity, "
            "EMAG2 magnetics, a geological map, a seismic interpretation, or a publication title."
        ),
        "source_uri": (
            "Optional but strongly recommended. Add a stable provider URL, DOI, catalogue page, map permalink, or "
            "publication link so reviewers can inspect the same source rather than relying on a screenshot."
        ),
        "source_resolution": (
            "Record the resolving power of the source when known: pixel size, grid spacing, map scale, seismic line "
            "spacing, survey vintage, or \"unknown\". Resolution helps reviewers judge whether the claimed feature is "
            "actually resolvable."
        ),
        "observed_feature": (
            "Summarise the actual observation in one sentence, for example \"partial annular ridge with drainage "
            "deflection\" or \"circular Bouguer gravity high with incomplete topographic rim\"."
        ),
        "endogenic_alternative": (
            "Give the strongest plausible non-impact explanation. Consider volcanic ring complexes, intrusions, "
            "diapirs, fold-thrust arcs, basin margins, drainage/erosion artefacts, source-boundary artefacts, or "
            "other regional geology. A useful submission tries to falsify itself."
        ),
        "independent_evidence": (
            "Select evidence classes that come from data beyond the visual trace. These tags are supportive context "
            "only; field petrography, geochemistry, and projectile material remain the classes most relevant to "
            "eventual confirmation."
        ),
        "original_trace_available": (
            "Check this when the line or polygon that defined the observation has been preserved, not merely a centre "
            "point. Original traces let reviewers compare the submitted geometry with terrain, source transitions, "
            "and alternative structures."
        ),
        "terms_confirmed": (
            "This acknowledgement keeps the catalogue aligned with the manuscript: circular or arcuate geometry, "
            "gravity-first ranking, and high scores can prioritise fieldwork, but they do not diagnose an impact origin."
        ),
    }
    FIELD_PLACEHOLDERS = {
        "title": "Neutral name, e.g. North Basin annular ridge",
        "description": "Describe the observation, continuity, data source, and why it warrants review.",
        "longitude": "24.750",
        "latitude": "-28.125",
        "diameter_km": "140",
        "source_title": "Dataset, map, imagery layer, survey, or paper title",
        "source_uri": "https://...",
        "source_resolution": "30 m pixels, 1:250 000 map, 2 arc-minute grid, or unknown",
        "observed_feature": "Partial annular ridge, gravity high, radial drainage pattern...",
        "endogenic_alternative": "Most plausible volcanic, tectonic, intrusive, erosional, or data-source explanation.",
    }
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, label in self.FIELD_LABELS.items():
            if field_name in self.fields:
                self.fields[field_name].label = label
        for field_name, help_text in self.FIELD_HELP_TEXT.items():
            if field_name in self.fields:
                self.fields[field_name].help_text = help_text
        for field_name, placeholder in self.FIELD_PLACEHOLDERS.items():
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.setdefault("placeholder", placeholder)

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
