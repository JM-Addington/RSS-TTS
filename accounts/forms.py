from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import (
    password_validators_help_texts,
    validate_password,
)
from django.core.exceptions import ValidationError


class BootstrapAuthenticationForm(AuthenticationForm):
    """Login form with Bootstrap form-control class on inputs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class CustomUserCreationForm(UserCreationForm):
    """Custom user creation form for Django's User model."""

    class Meta:
        model = User
        fields = ("username",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        # AIDEV-NOTE: Use plain text help_text so template can safely escape it (no |safe needed)
        self.fields["password1"].help_text = " ".join(
            password_validators_help_texts()
        )


# AIDEV-NOTE: validates via Django's AUTH_PASSWORD_VALIDATORS; user param enables UserAttributeSimilarityValidator
class AdminPasswordResetForm(forms.Form):
    """Form for admin password reset with full Django password validation."""

    new_password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "autocomplete": "new-password",
            }
        ),
        label="New Password",
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "autocomplete": "new-password",
            }
        ),
        label="Confirm New Password",
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["new_password"].help_text = " ".join(
            password_validators_help_texts()
        )

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_password")

        if new_password and confirm_password and new_password != confirm_password:
            raise ValidationError("Passwords do not match.")

        if new_password:
            try:
                validate_password(new_password, user=self.user)
            except ValidationError as e:
                self.add_error("new_password", e)

        return cleaned_data
