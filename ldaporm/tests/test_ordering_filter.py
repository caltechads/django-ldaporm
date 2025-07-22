"""
Unit tests for LdapOrderingFilter.

These tests focus on testing the filter logic without requiring a live LDAP connection.
"""

import unittest
import django
from unittest.mock import Mock, patch

from django.conf import settings

# Configure Django settings before any model is defined
if not settings.configured:
    settings.configure(
        LDAP_SERVERS={
            "test_server": {
                "read": {
                    "url": "ldap://localhost:389",
                    "user": "cn=admin,dc=example,dc=com",
                    "password": "admin",
                    "use_starttls": False,
                    "tls_verify": "never",
                    "timeout": 15.0,
                    "sizelimit": 1000,
                    "follow_referrals": False
                },
                "write": {
                    "url": "ldap://localhost:389",
                    "user": "cn=admin,dc=example,dc=com",
                    "password": "admin",
                    "use_starttls": False,
                    "tls_verify": "never",
                    "timeout": 15.0,
                    "sizelimit": 1000,
                    "follow_referrals": False
                }
            }
        },
        REST_FRAMEWORK={
            'DEFAULT_RENDERER_CLASSES': [
                'rest_framework.renderers.JSONRenderer',
            ],
            'DEFAULT_PARSER_CLASSES': [
                'rest_framework.parsers.JSONParser',
            ],
        },
        ALLOWED_HOSTS=['example.com', 'testserver', 'localhost', '127.0.0.1'],
        DEBUG=True,
    )
    try:
        django.setup()
    except Exception:
        pass

# Import REST framework after settings are configured
from rest_framework.test import APIRequestFactory
from rest_framework.exceptions import ValidationError

from ldaporm.restframework import LdapOrderingFilter


class MockLdapModel:
    """Mock LDAP model for testing."""

    class Meta:
        fields: list[str] = []
        ordering = ['uid']

    _meta = Meta

# Create field objects with proper name attributes
uid_field = Mock()
uid_field.name = 'uid'
cn_field = Mock()
cn_field.name = 'cn'
mail_field = Mock()
mail_field.name = 'mail'
created_field = Mock()
created_field.name = 'created'

MockLdapModel.Meta.fields = [uid_field, cn_field, mail_field, created_field]


class MockLdapQueryset:
    """Mock LDAP queryset for testing."""

    def __init__(self, model=None):
        self.model = model or MockLdapModel()

    def order_by(self, *args):
        """Mock order_by method."""
        return self


class MockViewSet:
    """Mock ViewSet for testing."""

    def __init__(self, ordering_fields=None, ordering=None):
        self.ordering_fields = ordering_fields
        if ordering is not None:
            self.ordering = ordering


class LdapOrderingFilterTestCase(unittest.TestCase):
    """Test cases for LdapOrderingFilter functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.factory = APIRequestFactory()
        self.filter_backend = LdapOrderingFilter()

    def test_get_ordering_single_field(self):
        """Test getting ordering for a single field."""
        request = self.factory.get('/api/users/?ordering=uid')
        request.query_params = {'ordering': 'uid'}
        view = MockViewSet(ordering_fields=['uid', 'cn', 'mail'])
        queryset = MockLdapQueryset()

        ordering = self.filter_backend.get_ordering(request, queryset, view)
        self.assertEqual(ordering, ['uid'])

    def test_get_ordering_multiple_fields(self):
        """Test getting ordering for multiple fields."""
        request = self.factory.get('/api/users/?ordering=uid,-cn,mail')
        request.query_params = {'ordering': 'uid,-cn,mail'}
        view = MockViewSet(ordering_fields=['uid', 'cn', 'mail'])
        queryset = MockLdapQueryset()

        ordering = self.filter_backend.get_ordering(request, queryset, view)
        self.assertEqual(ordering, ['uid', '-cn', 'mail'])

    def test_get_ordering_with_spaces(self):
        """Test getting ordering with spaces in the parameter."""
        request = self.factory.get('/api/users/?ordering=uid, -cn , mail')
        request.query_params = {'ordering': 'uid, -cn , mail'}
        view = MockViewSet(ordering_fields=['uid', 'cn', 'mail'])
        queryset = MockLdapQueryset()

        ordering = self.filter_backend.get_ordering(request, queryset, view)
        self.assertEqual(ordering, ['uid', '-cn', 'mail'])

    def test_get_ordering_empty_parameter(self):
        """Test getting ordering when no parameter is provided."""
        request = self.factory.get('/api/users/')
        request.query_params = {}
        view = MockViewSet(ordering=['cn'])
        queryset = MockLdapQueryset()

        ordering = self.filter_backend.get_ordering(request, queryset, view)
        self.assertEqual(ordering, ['cn'])

    def test_get_ordering_invalid_field(self):
        """Test that invalid fields are ignored gracefully."""
        request = self.factory.get('/api/users/?ordering=invalid_field')
        request.query_params = {'ordering': 'invalid_field'}
        view = MockViewSet(ordering_fields=['uid', 'cn', 'mail'])
        queryset = MockLdapQueryset()

        # Invalid fields should be ignored, not raise ValidationError
        ordering = self.filter_backend.get_ordering(request, queryset, view)
        self.assertEqual(ordering, [])  # No valid fields, so empty list

    def test_get_ordering_invalid_field_with_available_fields(self):
        """Test that invalid fields are ignored when available fields are specified."""
        request = self.factory.get('/api/users/?ordering=invalid_field')
        request.query_params = {'ordering': 'invalid_field'}
        view = MockViewSet(ordering_fields=['uid', 'cn', 'mail'])
        queryset = MockLdapQueryset()

        # Invalid fields should be ignored, not raise ValidationError
        ordering = self.filter_backend.get_ordering(request, queryset, view)
        self.assertEqual(ordering, [])  # No valid fields, so empty list

    def test_filter_queryset_with_ordering(self):
        """Test that filter_queryset applies ordering."""
        request = self.factory.get('/api/users/?ordering=cn')
        request.query_params = {'ordering': 'cn'}
        view = MockViewSet(ordering_fields=['uid', 'cn', 'mail'])
        queryset = MockLdapQueryset()

        # Mock the order_by method to track calls
        with patch.object(queryset, 'order_by') as mock_order_by:
            mock_order_by.return_value = queryset
            result = self.filter_backend.filter_queryset(request, queryset, view)

            # Verify order_by was called with the correct arguments
            mock_order_by.assert_called_once_with('cn')
            self.assertEqual(result, queryset)

    def test_filter_queryset_without_ordering(self):
        """Test that filter_queryset returns queryset unchanged when no ordering."""
        request = self.factory.get('/api/users/')
        request.query_params = {}
        view = MockViewSet()  # No ordering attribute
        queryset = MockLdapQueryset()

        # Mock the order_by method to track calls
        with patch.object(queryset, 'order_by') as mock_order_by:
            mock_order_by.return_value = queryset
            result = self.filter_backend.filter_queryset(request, queryset, view)

            # Verify order_by was called with default ordering from model
            mock_order_by.assert_called_once_with('uid')
            self.assertEqual(result, queryset)

    def test_get_default_ordering_from_view(self):
        """Test getting default ordering from view."""
        view = MockViewSet(ordering=['cn', 'mail'])
        queryset = MockLdapQueryset()

        ordering = self.filter_backend.get_default_ordering(view)
        self.assertEqual(ordering, ['cn', 'mail'])

    def test_get_default_ordering_from_model(self):
        """Test getting default ordering from model when view doesn't have it."""
        view = MockViewSet()  # No ordering attribute
        queryset = MockLdapQueryset()

        ordering = self.filter_backend.get_default_ordering(view, queryset)
        self.assertEqual(ordering, ['uid'])  # From MockLdapModel.Meta.ordering

    def test_is_valid_field_with_ordering_fields(self):
        """Test field validation when ordering_fields is specified."""
        view = MockViewSet(ordering_fields=['uid', 'cn', 'mail'])
        queryset = MockLdapQueryset()

        # Valid fields
        self.assertTrue(self.filter_backend._is_valid_field('uid', queryset, view))
        self.assertTrue(self.filter_backend._is_valid_field('-cn', queryset, view))

        # Invalid fields
        self.assertFalse(self.filter_backend._is_valid_field('invalid', queryset, view))
        self.assertFalse(self.filter_backend._is_valid_field('-invalid', queryset, view))

    def test_is_valid_field_without_ordering_fields(self):
        """Test field validation when ordering_fields is not specified."""
        view = MockViewSet()  # No ordering_fields
        queryset = MockLdapQueryset()

        # All model fields should be valid
        self.assertTrue(self.filter_backend._is_valid_field('uid', queryset, view))
        self.assertTrue(self.filter_backend._is_valid_field('cn', queryset, view))
        self.assertTrue(self.filter_backend._is_valid_field('mail', queryset, view))
        self.assertTrue(self.filter_backend._is_valid_field('created', queryset, view))

        # Invalid fields should still be invalid
        self.assertFalse(self.filter_backend._is_valid_field('invalid', queryset, view))

    def test_get_ordering_fields_from_view(self):
        """Test getting ordering fields from view."""
        view = MockViewSet(ordering_fields=['uid', 'cn'])
        ordering_fields = self.filter_backend._get_ordering_fields(view)
        self.assertEqual(ordering_fields, ['uid', 'cn'])

    def test_get_ordering_fields_from_filter(self):
        """Test getting ordering fields from filter when view doesn't have it."""
        view = MockViewSet()  # No ordering_fields
        self.filter_backend.ordering_fields = ['uid', 'cn', 'mail']

        ordering_fields = self.filter_backend._get_ordering_fields(view)
        self.assertEqual(ordering_fields, ['uid', 'cn', 'mail'])

    def test_get_available_fields_with_ordering_fields(self):
        """Test getting available fields when ordering_fields is specified."""
        view = MockViewSet(ordering_fields=['uid', 'cn', 'mail'])
        queryset = MockLdapQueryset()

        available_fields = self.filter_backend._get_available_fields(queryset, view)
        self.assertEqual(available_fields, ['uid', 'cn', 'mail'])

    def test_get_available_fields_without_ordering_fields(self):
        """Test getting available fields when ordering_fields is not specified."""
        view = MockViewSet()  # No ordering_fields
        queryset = MockLdapQueryset()

        available_fields = self.filter_backend._get_available_fields(queryset, view)
        self.assertEqual(available_fields, ['uid', 'cn', 'mail', 'created'])

    def test_get_schema_operation_parameters(self):
        """Test getting schema operation parameters for OpenAPI."""
        view = MockViewSet(ordering_fields=['uid', 'cn', 'mail'])
        queryset = MockLdapQueryset()

        # Mock get_queryset method
        view.get_queryset = lambda: queryset

        params = self.filter_backend.get_schema_operation_parameters(view)

        self.assertEqual(len(params), 1)
        param = params[0]
        self.assertEqual(param['name'], 'ordering')
        self.assertEqual(param['required'], False)
        self.assertEqual(param['in'], 'query')
        self.assertIn('Available fields: uid, cn, mail', param['description'])
        self.assertEqual(param['schema']['type'], 'string')
        self.assertEqual(param['schema']['example'], 'uid,-cn,mail')


if __name__ == '__main__':
    unittest.main()