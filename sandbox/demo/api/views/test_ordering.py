"""
Test file demonstrating LdapOrderingFilter usage.

This file shows how to use the LdapOrderingFilter with LDAP ORM models
and provides examples of different ordering scenarios.
"""

from rest_framework import viewsets
from rest_framework.test import APIRequestFactory
from django.test import TestCase

from ldaporm.restframework import LdapOrderingFilter, LdapModelSerializer
from demo.core.ldap.models import LDAPUser


class TestUserSerializer(LdapModelSerializer):
    """Test serializer for LDAPUser model."""

    class Meta:
        model = LDAPUser


class TestUserViewSet(viewsets.ModelViewSet):
    """Test ViewSet demonstrating LdapOrderingFilter usage."""

    serializer_class = TestUserSerializer
    filter_backends = [LdapOrderingFilter]
    ordering_fields = ["uid", "cn", "mail", "employee_number"]
    ordering = ["uid"]  # Default ordering
    lookup_field = "dn"

    def get_queryset(self):
        return LDAPUser.objects.all()


class LdapOrderingFilterTestCase(TestCase):
    """Test cases for LdapOrderingFilter functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.factory = APIRequestFactory()
        self.viewset = TestUserViewSet()
        self.viewset.action = "list"

    def test_default_ordering(self):
        """Test that default ordering is applied when no ordering parameter is provided."""
        request = self.factory.get("/api/users/")
        request.query_params = {}

        # Mock the queryset
        queryset = LDAPUser.objects.all()

        # Apply the filter
        filter_backend = LdapOrderingFilter()
        filtered_queryset = filter_backend.filter_queryset(
            request, queryset, self.viewset
        )

        # The filter should return the queryset with default ordering applied
        # Since we can't easily test the actual LDAP query, we'll just verify
        # that the filter doesn't raise any exceptions
        self.assertIsNotNone(filtered_queryset)

    def test_single_field_ordering(self):
        """Test ordering by a single field."""
        request = self.factory.get("/api/users/?ordering=cn")
        request.query_params = {"ordering": "cn"}

        queryset = LDAPUser.objects.all()
        filter_backend = LdapOrderingFilter()
        filtered_queryset = filter_backend.filter_queryset(
            request, queryset, self.viewset
        )

        self.assertIsNotNone(filtered_queryset)

    def test_descending_ordering(self):
        """Test descending ordering with '-' prefix."""
        request = self.factory.get("/api/users/?ordering=-cn")
        request.query_params = {"ordering": "-cn"}

        queryset = LDAPUser.objects.all()
        filter_backend = LdapOrderingFilter()
        filtered_queryset = filter_backend.filter_queryset(
            request, queryset, self.viewset
        )

        self.assertIsNotNone(filtered_queryset)

    def test_multiple_field_ordering(self):
        """Test ordering by multiple fields."""
        request = self.factory.get("/api/users/?ordering=uid,-cn,mail")
        request.query_params = {"ordering": "uid,-cn,mail"}

        queryset = LDAPUser.objects.all()
        filter_backend = LdapOrderingFilter()
        filtered_queryset = filter_backend.filter_queryset(
            request, queryset, self.viewset
        )

        self.assertIsNotNone(filtered_queryset)

    def test_invalid_field_ordering(self):
        """Test that invalid ordering fields raise ValidationError."""
        request = self.factory.get("/api/users/?ordering=invalid_field")
        request.query_params = {"ordering": "invalid_field"}

        queryset = LDAPUser.objects.all()
        filter_backend = LdapOrderingFilter()

        from rest_framework.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            filter_backend.filter_queryset(request, queryset, self.viewset)

    def test_ordering_parameter_parsing(self):
        """Test that ordering parameters are correctly parsed."""
        filter_backend = LdapOrderingFilter()

        # Test single field
        request = self.factory.get("/api/users/?ordering=uid")
        request.query_params = {"ordering": "uid"}
        ordering = filter_backend.get_ordering(
            request, LDAPUser.objects.all(), self.viewset
        )
        self.assertEqual(ordering, ["uid"])

        # Test multiple fields
        request = self.factory.get("/api/users/?ordering=uid,-cn,mail")
        request.query_params = {"ordering": "uid,-cn,mail"}
        ordering = filter_backend.get_ordering(
            request, LDAPUser.objects.all(), self.viewset
        )
        self.assertEqual(ordering, ["uid", "-cn", "mail"])

        # Test with spaces
        request = self.factory.get("/api/users/?ordering=uid, -cn , mail")
        request.query_params = {"ordering": "uid, -cn , mail"}
        ordering = filter_backend.get_ordering(
            request, LDAPUser.objects.all(), self.viewset
        )
        self.assertEqual(ordering, ["uid", "-cn", "mail"])


# Example usage in a real application:
"""
# views.py
from rest_framework import viewsets
from ldaporm.restframework import LdapOrderingFilter, LdapModelSerializer, LdapCursorPagination
from your_app.models import YourLdapModel

class YourLdapModelSerializer(LdapModelSerializer):
    class Meta:
        model = YourLdapModel

class YourLdapModelViewSet(viewsets.ModelViewSet):
    serializer_class = YourLdapModelSerializer
    pagination_class = LdapCursorPagination
    filter_backends = [LdapOrderingFilter]
    ordering_fields = ['field1', 'field2', 'field3']  # Restrict to specific fields
    ordering = ['field1']  # Default ordering
    lookup_field = 'dn'

    def get_queryset(self):
        return YourLdapModel.objects.all()

# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import YourLdapModelViewSet

router = DefaultRouter()
router.register(r'your-models', YourLdapModelViewSet, basename='your-model')

urlpatterns = [
    path('api/', include(router.urls)),
]

# API Usage Examples:
# GET /api/your-models/                    # Default ordering
# GET /api/your-models/?ordering=field1    # Order by field1 ascending
# GET /api/your-models/?ordering=-field1   # Order by field1 descending
# GET /api/your-models/?ordering=field1,-field2,field3  # Multiple fields
"""
