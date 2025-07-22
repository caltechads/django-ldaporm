from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from wildewidgets import WildewidgetDispatch

urlpatterns = [
    path("", include("demo.core.urls", namespace="core")),
    path("api/", include("demo.api.urls", namespace="api")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("admin/", include(admin.site.urls[:2], namespace=admin.site.name)),
    path("wildewidgets_json", WildewidgetDispatch.as_view(), name="wildewidgets_json"),
]


if settings.ENABLE_DEBUG_TOOLBAR:
    import debug_toolbar

    urlpatterns.append(path("__debug__/", include(debug_toolbar.urls)))
