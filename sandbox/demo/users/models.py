from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """
    User model for the demo application.
    """

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
