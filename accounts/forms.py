from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import password_validators_help_texts


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
