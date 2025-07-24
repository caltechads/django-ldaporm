from django.apps import AppConfig


class UsersConfig(AppConfig):
    name: str = "demo.users"
    label: str = "users"

    def ready(self):
        """Import admin module when app is ready."""
        from . import admin  # noqa: F401
