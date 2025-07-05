from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class CustomUserCreationForm(UserCreationForm):
    """Custom user creation form for Django's User model."""

    class Meta:
        model = User
        fields = ('username',)
