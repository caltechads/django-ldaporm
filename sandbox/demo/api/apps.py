from django.apps import AppConfig


class ApiConfig(AppConfig):
    """
    API example for LDAP operations.
    """

    name: str = "demo.api"
    verbose_name: str = "demo:api"
    app_name: str = "api"
