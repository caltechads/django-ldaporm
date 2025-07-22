from .settings import *  # noqa: F403


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "testdb",
    }
}

LDAP_SERVERS = {
    "default": {
        "basedn": "o=example,c=us",  # type: ignore[arg-type, assignment]
        "read": {
            "url": "ldap://localhost:389",  # type: ignore[arg-type, assignment]
            "user": None,
            "password": None,
        },
        "write": {
            "url": "ldap://localhost:389",  # type: ignore[arg-type, assignment]
            "user": None,
            "password": None,
        },
    }
}

# REST Framework settings for testing
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    "DEFAULT_FILTER_BACKENDS": [],
    "DEFAULT_ORDERING": [],
}
