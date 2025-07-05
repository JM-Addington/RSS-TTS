# Import the UserProfile model and its extensions
from .models_profile import UserProfile  # noqa: F401

# The UserProfile model extends Django's built-in User model
# This approach is safer for existing installations as it doesn't require
# changing AUTH_USER_MODEL
