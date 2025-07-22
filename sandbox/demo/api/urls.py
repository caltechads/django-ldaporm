from django.urls import include, path
from rest_framework import routers

from .views.groups import LDAPGroupViewSet
from .views.roles import NSRoleViewSet
from .views.users import LDAPUserViewSet

app_name = "api"

# Create a router and register our viewsets with it
router = routers.DefaultRouter()
router.register(r"users", LDAPUserViewSet, basename="ldap-user")
router.register(r"groups", LDAPGroupViewSet, basename="ldap-group")
router.register(r"roles", NSRoleViewSet, basename="ldap-role")

# The API URLs are now determined automatically by the router
urlpatterns = [
    path("", include(router.urls)),
]
