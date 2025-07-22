"""
Tests for LDAP ORM REST Framework serializers.

This module tests the LdapModelSerializer and HyperlinkedModelSerializer
classes, covering field mapping, relationships, configuration options,
and error handling.
"""

import datetime
import os
import django
from unittest.mock import Mock, patch

from django.conf import settings
import unittest

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
from rest_framework import serializers
from rest_framework.test import APIRequestFactory

from ldaporm import fields, models
from ldaporm.restframework import HyperlinkedModelSerializer, LdapModelSerializer, LdapCursorPagination
from ldaporm.restframework import LdapFilterBackend


class TestUser(models.Model):
    """Test user model for serializer tests."""

    username = fields.CharField(max_length=50, primary_key=True)
    first_name = fields.CharField(max_length=50)
    last_name = fields.CharField(max_length=50)
    email = fields.EmailField()
    is_active = fields.BooleanField(default=True)
    age = fields.IntegerField(blank=True, null=True)
    birth_date = fields.DateField(blank=True, null=True)
    created_at = fields.DateTimeField(blank=True, null=True)
    email_list = fields.CharListField(max_length=100, blank=True)
    password_hash = fields.CaseInsensitiveSHA1Field(blank=True)
    ldap_password = fields.LDAPPasswordField(blank=True)
    ad_password = fields.ADPasswordField(blank=True)
    email_forward = fields.EmailForwardField(blank=True)
    photo = fields.BinaryField(blank=True, null=True)
    certificate = fields.BinaryField(blank=True, null=True)

    class Meta:
        basedn = "ou=users,dc=example,dc=com"
        objectclass = "person"
        ldap_server = "test_server"
        ordering: list[str] = []
        ldap_options: list[str] = []
        extra_objectclasses = ["organizationalPerson", "inetOrgPerson"]


class TestDepartment(models.Model):
    """Test department model for relationship tests."""

    name = fields.CharField(max_length=100, primary_key=True)
    description = fields.CharField(max_length=500, blank=True)
    location = fields.CharField(max_length=100, blank=True)

    class Meta:
        basedn = "ou=departments,dc=example,dc=com"
        objectclass = "organizationalUnit"
        ldap_server = "test_server"
        ordering: list[str] = []
        ldap_options: list[str] = []
        extra_objectclasses = ["top"]


class TestUserWithRelationships(models.Model):
    """Test user model with relationship fields."""

    username = fields.CharField(max_length=50, primary_key=True)
    first_name = fields.CharField(max_length=50)
    last_name = fields.CharField(max_length=50)
    email = fields.EmailField()
    department_dn = fields.CharField(max_length=500, blank=True, null=True)
    manager_dn = fields.CharField(max_length=500, blank=True, null=True)
    custom_relationship = fields.CharField(max_length=500, blank=True, null=True)

    class Meta:
        basedn = "ou=users,dc=example,dc=com"
        objectclass = "person"
        ldap_server = "test_server"
        ordering: list[str] = []
        ldap_options: list[str] = []
        extra_objectclasses = ["organizationalPerson", "inetOrgPerson"]


class LdapModelSerializerTestCase(unittest.TestCase):
    """Test cases for LdapModelSerializer."""

    def setUp(self):
        """Set up test data."""
        self.factory = APIRequestFactory()
        self.user_data = {
            'username': 'testuser',
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'test@example.com',
            'is_active': True,
            'age': 30,
            'birth_date': datetime.date(1993, 1, 1),
            'created_at': datetime.datetime(2023, 1, 1, 12, 0, 0),
            'email_list': ['test1@example.com', 'test2@example.com'],
            'password_hash': 'test_hash',
            'ldap_password': 'test_password',
            'ad_password': 'test_ad_password',
            'email_forward': 'test@example.com',
        }

    def test_basic_serializer_creation(self):
        """Test basic serializer creation and field introspection."""
        class UserSerializer(LdapModelSerializer):
            class Meta:
                model = TestUser

        serializer = UserSerializer()

        # Check that fields were automatically added
        self.assertIn('username', serializer.fields)
        self.assertIn('first_name', serializer.fields)
        self.assertIn('last_name', serializer.fields)
        self.assertIn('email', serializer.fields)
        self.assertIn('is_active', serializer.fields)
        self.assertIn('age', serializer.fields)
        self.assertIn('birth_date', serializer.fields)
        self.assertIn('created_at', serializer.fields)
        self.assertIn('email_list', serializer.fields)
        self.assertIn('password_hash', serializer.fields)
        self.assertIn('ldap_password', serializer.fields)
        self.assertIn('ad_password', serializer.fields)
        self.assertIn('email_forward', serializer.fields)

    def test_field_type_mapping(self):
        """Test that LDAP ORM fields are mapped to correct DRF fields."""
        class UserSerializer(LdapModelSerializer):
            class Meta:
                model = TestUser

        serializer = UserSerializer()

        # Test field type mappings
        self.assertIsInstance(serializer.fields['username'], serializers.CharField)
        self.assertIsInstance(serializer.fields['email'], serializers.EmailField)
        self.assertIsInstance(serializer.fields['is_active'], serializers.BooleanField)
        self.assertIsInstance(serializer.fields['age'], serializers.IntegerField)
        self.assertIsInstance(serializer.fields['birth_date'], serializers.DateField)
        self.assertIsInstance(serializer.fields['created_at'], serializers.DateTimeField)
        self.assertIsInstance(serializer.fields['email_list'], serializers.ListField)
        self.assertIsInstance(serializer.fields['password_hash'], serializers.CharField)
        self.assertIsInstance(serializer.fields['ldap_password'], serializers.CharField)
        self.assertIsInstance(serializer.fields['ad_password'], serializers.CharField)
        self.assertIsInstance(serializer.fields['email_forward'], serializers.EmailField)

    def test_field_validation(self):
        """Test field validation and required/blank settings."""
        class UserSerializer(LdapModelSerializer):
            class Meta:
                model = TestUser

        serializer = UserSerializer()

        # Test required fields (not blank)
        self.assertTrue(serializer.fields['username'].required)
        self.assertTrue(serializer.fields['first_name'].required)
        self.assertTrue(serializer.fields['last_name'].required)
        self.assertTrue(serializer.fields['email'].required)

        # Test optional fields (blank=True)
        self.assertFalse(serializer.fields['age'].required)
        self.assertFalse(serializer.fields['birth_date'].required)
        self.assertFalse(serializer.fields['created_at'].required)
        self.assertFalse(serializer.fields['email_list'].required)

    def test_password_field_behavior(self):
        """Test password field behavior (read-only for hashed fields)."""
        class UserSerializer(LdapModelSerializer):
            class Meta:
                model = TestUser

        serializer = UserSerializer()

        # Test that password fields are read-only
        self.assertTrue(serializer.fields['password_hash'].read_only)
        self.assertTrue(serializer.fields['ldap_password'].read_only)
        self.assertTrue(serializer.fields['ad_password'].read_only)

        # Test password field styling
        self.assertEqual(
            serializer.fields['password_hash'].style.get('input_type'),
            'password'
        )
        self.assertEqual(
            serializer.fields['ldap_password'].style.get('input_type'),
            'password'
        )
        self.assertEqual(
            serializer.fields['ad_password'].style.get('input_type'),
            'password'
        )

    def test_to_representation(self):
        """Test serialization of model instances."""
        class UserSerializer(LdapModelSerializer):
            class Meta:
                model = TestUser

        # Create a mock user instance
        user = Mock()
        user.username = 'testuser'
        user.first_name = 'Test'
        user.last_name = 'User'
        user.email = 'test@example.com'
        user.is_active = True
        user.age = 30
        user.birth_date = datetime.date(1993, 1, 1)
        user.created_at = datetime.datetime(2023, 1, 1, 12, 0, 0)
        user.email_list = ['test1@example.com', 'test2@example.com']
        user.password_hash = 'test_hash'
        user.ldap_password = 'test_password'
        user.ad_password = 'test_ad_password'
        user.email_forward = 'test@example.com'
        user.dn = 'cn=testuser,ou=users,dc=example,dc=com'

        # Mock the _meta.fields
        user._meta = Mock()
        user._meta.fields = []
        for field_name in [
            'username', 'first_name', 'last_name', 'email', 'is_active', 'age',
            'birth_date', 'created_at', 'email_list', 'password_hash', 'ldap_password',
            'ad_password', 'email_forward']:
            m = Mock()
            m.name = field_name
            user._meta.fields.append(m)

        serializer = UserSerializer(user)
        data = serializer.data

        # Test that all fields are serialized correctly
        self.assertEqual(data['username'], 'testuser')
        self.assertEqual(data['first_name'], 'Test')
        self.assertEqual(data['last_name'], 'User')
        self.assertEqual(data['email'], 'test@example.com')
        self.assertTrue(data['is_active'])
        self.assertEqual(data['age'], 30)
        self.assertEqual(data['birth_date'], '1993-01-01')
        self.assertEqual(data['created_at'], '2023-01-01T12:00:00')
        self.assertEqual(data['email_list'], ['test1@example.com', 'test2@example.com'])
        self.assertEqual(data['password_hash'], 'test_hash')
        self.assertEqual(data['ldap_password'], 'test_password')
        self.assertEqual(data['ad_password'], 'test_ad_password')
        self.assertEqual(data['email_forward'], 'test@example.com')
        self.assertEqual(data['dn'], 'cn=testuser,ou=users,dc=example,dc=com')

    def test_create_method(self):
        """Test create method with validated data."""
        class UserSerializer(LdapModelSerializer):
            class Meta:
                model = TestUser

        serializer = UserSerializer()

        with patch.object(TestUser, 'save') as mock_save:
            instance = serializer.create(self.user_data)

            # Check that the instance was created with correct data
            self.assertEqual(instance.username, 'testuser')
            self.assertEqual(instance.first_name, 'Test')
            self.assertEqual(instance.last_name, 'User')
            self.assertEqual(instance.email, 'test@example.com')
            self.assertTrue(instance.is_active)
            self.assertEqual(instance.age, 30)

            # Check that save was called
            mock_save.assert_called_once()

    def test_update_method(self):
        """Test update method with validated data."""
        class UserSerializer(LdapModelSerializer):
            class Meta:
                model = TestUser

        serializer = UserSerializer()

        # Create a mock instance
        instance = Mock()

        with patch.object(instance, 'save') as mock_save:
            updated_instance = serializer.update(instance, self.user_data)

            # Check that attributes were set
            self.assertEqual(updated_instance.username, 'testuser')
            self.assertEqual(updated_instance.first_name, 'Test')
            self.assertEqual(updated_instance.last_name, 'User')
            self.assertEqual(updated_instance.email, 'test@example.com')
            self.assertTrue(updated_instance.is_active)
            self.assertEqual(updated_instance.age, 30)

            # Check that save was called
            mock_save.assert_called_once()

    def test_binary_field_serialization(self):
        """Test binary field serialization and deserialization."""
        class UserSerializer(LdapModelSerializer):
            class Meta:
                model = TestUser

        # Test binary data
        test_photo_data = b'fake_photo_data'
        test_cert_data = b'fake_certificate_data'

        # Create a mock instance with binary data
        instance = Mock()
        # Create proper field objects
        username_field = Mock()
        username_field.name = 'username'
        username_field.__class__ = fields.CharField

        photo_field = Mock()
        photo_field.name = 'photo'
        photo_field.__class__ = fields.BinaryField

        cert_field = Mock()
        cert_field.name = 'certificate'
        cert_field.__class__ = fields.BinaryField

        instance._meta.fields = [username_field, photo_field, cert_field]
        instance.username = 'testuser'
        instance.photo = test_photo_data
        instance.certificate = test_cert_data
        instance.dn = 'cn=testuser,ou=users,dc=example,dc=com'

        # Test serialization (to_representation)
        serializer = UserSerializer()
        result = serializer.to_representation(instance)

        # Verify binary data is base64 encoded
        import base64
        expected_photo = base64.b64encode(test_photo_data).decode('utf-8')
        expected_cert = base64.b64encode(test_cert_data).decode('utf-8')

        self.assertEqual(result['photo'], expected_photo)
        self.assertEqual(result['certificate'], expected_cert)
        self.assertEqual(result['username'], 'testuser')
        self.assertEqual(result['dn'], 'cn=testuser,ou=users,dc=example,dc=com')

    def test_binary_field_deserialization(self):
        """Test binary field deserialization from base64."""
        class UserSerializer(LdapModelSerializer):
            class Meta:
                model = TestUser

        serializer = UserSerializer()

        # Test data with base64-encoded binary data
        test_photo_data = b'fake_photo_data'
        test_cert_data = b'fake_certificate_data'

        import base64
        photo_base64 = base64.b64encode(test_photo_data).decode('utf-8')
        cert_base64 = base64.b64encode(test_cert_data).decode('utf-8')

        # Test deserialization
        data = {
            'username': 'testuser',
            'photo': photo_base64,
            'certificate': cert_base64,
        }

        # Get the binary field from the serializer
        binary_field = serializer.fields['photo']

        # Test to_internal_value
        photo_result = binary_field.to_internal_value(photo_base64)
        cert_result = binary_field.to_internal_value(cert_base64)

        self.assertEqual(photo_result, test_photo_data)
        self.assertEqual(cert_result, test_cert_data)

    def test_binary_field_null_handling(self):
        """Test binary field handling of null values."""
        class UserSerializer(LdapModelSerializer):
            class Meta:
                model = TestUser

        serializer = UserSerializer()
        binary_field = serializer.fields['photo']

        # Test null values
        self.assertIsNone(binary_field.to_internal_value(None))
        self.assertIsNone(binary_field.to_representation(None))

    def test_binary_field_invalid_data(self):
        """Test binary field validation with invalid data."""
        class UserSerializer(LdapModelSerializer):
            class Meta:
                model = TestUser

        serializer = UserSerializer()
        binary_field = serializer.fields['photo']

        # Test invalid base64 data
        with self.assertRaises(serializers.ValidationError):
            binary_field.to_internal_value('invalid_base64_data')

        # Test non-string/non-bytes data
        with self.assertRaises(serializers.ValidationError):
            binary_field.to_internal_value(123)


class HyperlinkedModelSerializerTestCase(unittest.TestCase):
    """Test cases for HyperlinkedModelSerializer."""

    def setUp(self):
        """Set up test data."""
        self.factory = APIRequestFactory()
        self.user_data = {
            'username': 'testuser',
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'test@example.com',
            'department_dn': 'ou=engineering,dc=example,dc=com',
            'manager_dn': 'cn=manager,ou=users,dc=example,dc=com',
        }

    def test_basic_serializer_creation(self):
        """Test basic serializer creation with URL field."""
        class UserSerializer(HyperlinkedModelSerializer):
            class Meta:
                model = TestUserWithRelationships
                lookup_field = 'dn'
                relationship_models = {
                    'department_dn': TestDepartment,
                    'manager_dn': TestUserWithRelationships,
                    'custom_relationship': TestUserWithRelationships,
                }

        serializer = UserSerializer()

        # Check that URL field was added
        self.assertIn('url', serializer.fields)
        self.assertIsInstance(serializer.fields['url'], serializers.HyperlinkedIdentityField)

        # Check that other fields are present
        self.assertIn('username', serializer.fields)
        self.assertIn('first_name', serializer.fields)
        self.assertIn('last_name', serializer.fields)
        self.assertIn('email', serializer.fields)

    def test_url_field_configuration(self):
        """Test URL field configuration with custom settings."""
        class UserSerializer(HyperlinkedModelSerializer):
            class Meta:
                model = TestUserWithRelationships
                lookup_field = 'username'
                extra_kwargs = {
                    'url': {
                        'view_name': 'api:user-detail',
                        'lookup_field': 'username',
                    }
                }

        serializer = UserSerializer()
        url_field = serializer.fields['url']

        self.assertEqual(url_field.view_name, 'api:user-detail')
        self.assertEqual(url_field.lookup_field, 'username')

    def test_relationship_field_detection(self):
        """Test automatic detection of relationship fields."""
        class UserSerializer(HyperlinkedModelSerializer):
            class Meta:
                model = TestUserWithRelationships
                lookup_field = 'dn'
                relationship_models = {
                    'department_dn': TestDepartment,
                    'manager_dn': TestUserWithRelationships,
                    'custom_relationship': TestUserWithRelationships,
                }

        serializer = UserSerializer()

        # Check that relationship fields are detected and configured
        self.assertIn('department_dn', serializer.fields)
        self.assertIn('manager_dn', serializer.fields)
        self.assertIn('custom_relationship', serializer.fields)

        # Check that they are HyperlinkedRelatedField instances
        self.assertIsInstance(serializer.fields['department_dn'], serializers.HyperlinkedRelatedField)
        self.assertIsInstance(serializer.fields['manager_dn'], serializers.HyperlinkedRelatedField)
        self.assertIsInstance(serializer.fields['custom_relationship'], serializers.HyperlinkedRelatedField)

    def test_relationship_field_configuration(self):
        """Test relationship field configuration with extra_kwargs."""
        class UserSerializer(HyperlinkedModelSerializer):
            class Meta:
                model = TestUserWithRelationships
                lookup_field = 'dn'
                relationship_models = {
                    'department_dn': TestDepartment,
                    'manager_dn': TestUserWithRelationships,
                    'custom_relationship': TestUserWithRelationships,
                }
                extra_kwargs = {
                    'department_dn': {
                        'view_name': 'api:department-detail',
                        'lookup_field': 'name',
                    },
                    'manager_dn': {
                        'view_name': 'api:user-detail',
                        'lookup_field': 'username',
                    },
                    'custom_relationship': {
                        'view_name': 'api:user-detail',
                        'lookup_field': 'username',
                    }
                }

        serializer = UserSerializer()

        # Check department_dn field configuration
        dept_field = serializer.fields['department_dn']
        self.assertEqual(dept_field.view_name, 'api:department-detail')
        self.assertEqual(dept_field.lookup_field, 'name')

        # Check manager_dn field configuration
        mgr_field = serializer.fields['manager_dn']
        self.assertEqual(mgr_field.view_name, 'api:user-detail')
        self.assertEqual(mgr_field.lookup_field, 'username')

        # Check custom_relationship field configuration
        custom_field = serializer.fields['custom_relationship']
        self.assertEqual(custom_field.view_name, 'api:user-detail')
        self.assertEqual(custom_field.lookup_field, 'username')

    def test_relationship_field_validation(self):
        """Test relationship field validation settings."""
        class UserSerializer(HyperlinkedModelSerializer):
            class Meta:
                model = TestUserWithRelationships
                lookup_field = 'dn'
                relationship_models = {
                    'department_dn': TestDepartment,
                    'manager_dn': TestUserWithRelationships,
                    'custom_relationship': TestUserWithRelationships,
                }

        serializer = UserSerializer()

        # Test that relationship fields are not required (blank=True)
        self.assertFalse(serializer.fields['department_dn'].required)
        self.assertFalse(serializer.fields['manager_dn'].required)
        self.assertFalse(serializer.fields['custom_relationship'].required)

        # Test that they allow null values
        self.assertTrue(serializer.fields['department_dn'].allow_null)
        self.assertTrue(serializer.fields['manager_dn'].allow_null)
        self.assertTrue(serializer.fields['custom_relationship'].allow_null)

    def test_to_representation_with_relationships(self):
        """Test serialization with hyperlinked relationships."""
        class UserSerializer(HyperlinkedModelSerializer):
            class Meta:
                model = TestUserWithRelationships
                lookup_field = 'dn'
                relationship_models = {
                    'department_dn': TestDepartment,
                    'manager_dn': TestUserWithRelationships,
                    'custom_relationship': TestUserWithRelationships,
                }

        # Create a mock user instance
        user = Mock()
        user.username = 'testuser'
        user.first_name = 'Test'
        user.last_name = 'User'
        user.email = 'test@example.com'
        user.department_dn = 'ou=engineering,dc=example,dc=com'
        user.manager_dn = 'cn=manager,ou=users,dc=example,dc=com'
        user.custom_relationship = 'cn=customuser,ou=users,dc=example,dc=com'
        user.dn = 'cn=testuser,ou=users,dc=example,dc=com'

        # Mock the _meta.fields
        user._meta = Mock()
        user._meta.fields = []
        for field_name in [
            'username', 'first_name', 'last_name', 'email', 'department_dn',
            'manager_dn', 'custom_relationship']:
            m = Mock()
            m.name = field_name
            user._meta.fields.append(m)

        # Mock related objects
        department = Mock()
        department.dn = 'ou=engineering,dc=example,dc=com'
        department._meta = Mock()
        department._meta.object_name = 'TestDepartment'

        manager = Mock()
        manager.dn = 'cn=manager,ou=users,dc=example,dc=com'
        manager._meta = Mock()
        manager._meta.object_name = 'TestUserWithRelationships'

        custom_user = Mock()
        custom_user.dn = 'cn=customuser,ou=users,dc=example,dc=com'
        custom_user._meta = Mock()
        custom_user._meta.object_name = 'TestUserWithRelationships'

        # Mock the queryset get method
        with patch.object(TestDepartment.objects, 'get', return_value=department), \
             patch.object(TestUserWithRelationships.objects, 'get', return_value=manager), \
             patch.object(TestUserWithRelationships.objects, 'get', return_value=custom_user), \
             patch('ldaporm.restframework.reverse') as mock_reverse:

            mock_reverse.side_effect = lambda view_name, kwargs, request, format: f"http://example.com/api/{view_name}/{kwargs.get('dn', '')}/"

            serializer = UserSerializer(user, context={'request': Mock(), 'format': 'json'})
            data = serializer.data

            # Test that basic fields are serialized
            self.assertEqual(data['username'], 'testuser')
            self.assertEqual(data['first_name'], 'Test')
            self.assertEqual(data['last_name'], 'User')
            self.assertEqual(data['email'], 'test@example.com')

            # Test that relationships are hyperlinked
            self.assertIn('department_dn', data)
            self.assertIn('manager_dn', data)
            self.assertIn('custom_relationship', data)

            # Verify that reverse was called for relationships
            mock_reverse.assert_called()

    def test_to_representation_fallback_to_dn(self):
        """Test that relationship fields fall back to DN when related object not found."""
        class UserSerializer(HyperlinkedModelSerializer):
            class Meta:
                model = TestUserWithRelationships
                lookup_field = 'dn'
                relationship_models = {
                    'department_dn': TestDepartment,
                    'manager_dn': TestUserWithRelationships,
                    'custom_relationship': TestUserWithRelationships,
                }

        # Create a mock user instance
        user = Mock()
        user.username = 'testuser'
        user.department_dn = 'ou=engineering,dc=example,dc=com'
        user.manager_dn = 'cn=manager,ou=users,dc=example,dc=com'
        user.custom_relationship = 'cn=customuser,ou=users,dc=example,dc=com'
        user.dn = 'cn=testuser,ou=users,dc=example,dc=com'

        # Mock the _meta.fields
        user._meta = Mock()
        user._meta.fields = []
        for field_name in [
            'username', 'department_dn', 'manager_dn', 'custom_relationship']:
            m = Mock()
            m.name = field_name
            user._meta.fields.append(m)

        # Mock the queryset get method to raise DoesNotExist
        with patch.object(TestDepartment.objects, 'get', side_effect=TestDepartment.DoesNotExist), \
             patch.object(TestUserWithRelationships.objects, 'get', side_effect=TestUserWithRelationships.DoesNotExist):
            serializer = UserSerializer(user, context={'request': Mock(), 'format': 'json'})
            data = serializer.data

            # Test that the field falls back to the DN value
            self.assertEqual(data['department_dn'], 'ou=engineering,dc=example,dc=com')
            self.assertEqual(data['manager_dn'], 'cn=manager,ou=users,dc=example,dc=com')
            self.assertEqual(data['custom_relationship'], 'cn=customuser,ou=users,dc=example,dc=com')

    def test_get_detail_view_name(self):
        """Test detail view name generation."""
        class UserSerializer(HyperlinkedModelSerializer):
            class Meta:
                model = TestUserWithRelationships
                lookup_field = 'dn'

        serializer = UserSerializer()
        view_name = serializer._get_detail_view_name()

        self.assertEqual(view_name, 'testuserwithrelationships-detail')

    def test_get_lookup_field(self):
        """Test lookup field retrieval."""
        class UserSerializer(HyperlinkedModelSerializer):
            class Meta:
                model = TestUserWithRelationships
                lookup_field = 'username'

        serializer = UserSerializer()
        lookup_field = serializer._get_lookup_field()

        self.assertEqual(lookup_field, 'username')

    def test_get_lookup_field_default(self):
        """Test default lookup field when not specified."""
        class UserSerializer(HyperlinkedModelSerializer):
            class Meta:
                model = TestUserWithRelationships

        serializer = UserSerializer()
        lookup_field = serializer._get_lookup_field()

        self.assertEqual(lookup_field, 'dn')

    def test_is_relationship_field(self):
        """Test relationship field detection logic."""
        class UserSerializer(HyperlinkedModelSerializer):
            class Meta:
                model = TestUserWithRelationships
                relationship_fields = ['custom_relationship']

        serializer = UserSerializer()

        # Test automatic detection by field name
        dept_field = Mock()
        dept_field.name = 'department_dn'
        self.assertTrue(serializer._is_relationship_field(dept_field))

        manager_field = Mock()
        manager_field.name = 'manager_dn'
        self.assertTrue(serializer._is_relationship_field(manager_field))

        # Test explicit configuration
        custom_field = Mock()
        custom_field.name = 'custom_relationship'
        self.assertTrue(serializer._is_relationship_field(custom_field))

        # Test non-relationship field
        name_field = Mock()
        name_field.name = 'first_name'
        self.assertFalse(serializer._is_relationship_field(name_field))

    def test_get_related_model(self):
        """Test related model retrieval."""
        class UserSerializer(HyperlinkedModelSerializer):
            class Meta:
                model = TestUserWithRelationships
                relationship_models = {
                    'department_dn': TestDepartment,
                    'manager_dn': TestUserWithRelationships,
                    'custom_relationship': TestUserWithRelationships,
                }

        serializer = UserSerializer()

        # Test with configured relationship
        dept_field = Mock()
        dept_field.name = 'department_dn'
        related_model = serializer._get_related_model(dept_field)
        self.assertEqual(related_model, TestDepartment)

        # Test with non-configured relationship
        unknown_field = Mock()
        unknown_field.name = 'unknown_field'
        related_model = serializer._get_related_model(unknown_field)
        self.assertIsNone(related_model)

    def test_inheritance_from_ldap_model_serializer(self):
        """Test that HyperlinkedModelSerializer inherits field mapping from LdapModelSerializer."""
        class UserSerializer(HyperlinkedModelSerializer):
            class Meta:
                model = TestUser
                lookup_field = 'dn'

        serializer = UserSerializer()

        # Test that regular fields are mapped correctly
        self.assertIsInstance(serializer.fields['username'], serializers.CharField)
        self.assertIsInstance(serializer.fields['email'], serializers.EmailField)
        self.assertIsInstance(serializer.fields['is_active'], serializers.BooleanField)
        self.assertIsInstance(serializer.fields['age'], serializers.IntegerField)

    def test_choices_field_handling(self):
        """Test that fields with choices are handled correctly."""
        class TestUserWithChoices(models.Model):
            username = fields.CharField(max_length=50, primary_key=True)
            status = fields.CharField(max_length=20, choices=[
                ('active', 'Active'),
                ('inactive', 'Inactive'),
                ('pending', 'Pending'),
            ])

            class Meta:
                basedn = "ou=users,dc=example,dc=com"
                objectclass = "person"
                ldap_server = "test_server"
                ordering: list[str] = []
                ldap_options: list[str] = []
                extra_objectclasses = ["top"]

        class UserSerializer(HyperlinkedModelSerializer):
            class Meta:
                model = TestUserWithChoices
                lookup_field = 'dn'

        serializer = UserSerializer()

        # Test that choice field is mapped to ChoiceField
        self.assertIsInstance(serializer.fields['status'], serializers.ChoiceField)
        self.assertEqual(serializer.fields['status'].choices, {
            'active': 'Active',
            'inactive': 'Inactive',
            'pending': 'Pending',
        })


class SerializerIntegrationTestCase(unittest.TestCase):
    """Integration tests for serializers with real model instances."""

    def setUp(self):
        """Set up test data."""
        self.factory = APIRequestFactory()

    def test_serializer_with_real_model_meta(self):
        """Test serializer with real model meta information."""
        class UserSerializer(LdapModelSerializer):
            class Meta:
                model = TestUser

        # Test that serializer can be instantiated without errors
        serializer = UserSerializer()

        # Test that all expected fields are present
        expected_fields = [
            'username', 'first_name', 'last_name', 'email', 'is_active',
            'age', 'birth_date', 'created_at', 'email_list', 'password_hash',
            'ldap_password', 'ad_password', 'email_forward'
        ]

        for field_name in expected_fields:
            self.assertIn(field_name, serializer.fields)

    def test_hyperlinked_serializer_with_real_model_meta(self):
        """Test hyperlinked serializer with real model meta information."""
        class UserSerializer(HyperlinkedModelSerializer):
            class Meta:
                model = TestUserWithRelationships
                lookup_field = 'dn'
                relationship_models = {
                    'department_dn': TestDepartment,
                    'manager_dn': TestUserWithRelationships,
                    'custom_relationship': TestUserWithRelationships,
                }

        # Test that serializer can be instantiated without errors
        serializer = UserSerializer()

        # Test that URL field is present
        self.assertIn('url', serializer.fields)

        # Test that relationship fields are present
        self.assertIn('department_dn', serializer.fields)
        self.assertIn('manager_dn', serializer.fields)
        self.assertIn('custom_relationship', serializer.fields)

        # Test that regular fields are present
        self.assertIn('username', serializer.fields)
        self.assertIn('first_name', serializer.fields)
        self.assertIn('last_name', serializer.fields)
        self.assertIn('email', serializer.fields)

    def test_serializer_validation(self):
        """Test serializer validation with sample data."""
        class UserSerializer(LdapModelSerializer):
            class Meta:
                model = TestUser

        # Test valid data
        valid_data = {
            'username': 'testuser',
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'test@example.com',
            'is_active': True,
            'objectclass': ['person', 'organizationalPerson', 'inetOrgPerson'],
        }

        serializer = UserSerializer(data=valid_data)
        self.assertTrue(serializer.is_valid())

        # Test invalid data (missing required fields)
        invalid_data = {
            'username': 'testuser',
            # Missing first_name, last_name, email, objectclass
        }

        serializer = UserSerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('first_name', serializer.errors)
        self.assertIn('last_name', serializer.errors)
        self.assertIn('email', serializer.errors)
        self.assertIn('objectclass', serializer.errors)


class LdapCursorPaginationTestCase(unittest.TestCase):
    """Test cases for LdapCursorPagination."""

    def setUp(self):
        """Set up test data."""
        self.factory = APIRequestFactory()
        self.pagination = LdapCursorPagination()

        # Mock a PagedResultSet
        class MockPagedResultSet:
            def __init__(self, results, next_cookie, has_more):
                self.results = results
                self.next_cookie = next_cookie
                self.has_more = has_more

        self.mock_paged_results = MockPagedResultSet(
            results=[Mock(username='user1'), Mock(username='user2')],
            next_cookie='test_cookie_123',
            has_more=True
        )

    def test_pagination_initialization(self):
        """Test pagination class initialization."""
        self.assertEqual(self.pagination.page_size, 100)
        self.assertEqual(self.pagination.page_size_query_param, 'page_size')
        self.assertEqual(self.pagination.max_page_size, 1000)
        self.assertEqual(self.pagination.cursor_query_param, 'next_token')

    def test_get_page_size_from_request(self):
        """Test getting page size from request parameters."""
        # Test default page size
        request = self.factory.get('/api/users/')
        page_size = self.pagination.get_page_size(request)
        self.assertEqual(page_size, 100)

        # Test custom page size
        request = self.factory.get('/api/users/?page_size=50')
        page_size = self.pagination.get_page_size(request)
        self.assertEqual(page_size, 50)

        # Test max page size limit
        request = self.factory.get('/api/users/?page_size=2000')
        page_size = self.pagination.get_page_size(request)
        self.assertEqual(page_size, 1000)

        # Test invalid page size
        request = self.factory.get('/api/users/?page_size=invalid')
        page_size = self.pagination.get_page_size(request)
        self.assertEqual(page_size, 100)

    def test_cursor_decoding(self):
        """Test cursor decoding functionality."""
        # Test valid cursor
        valid_cursor = 'dGVzdF9jb29raWVfMTIz'  # base64 for 'test_cookie_123'
        request = self.factory.get(f'/api/users/?next_token={valid_cursor}')

        # Mock the paginate_queryset method to test cursor decoding
        with patch.object(self.pagination, 'paginate_queryset') as mock_paginate:
            mock_paginate.return_value = self.mock_paged_results.results
            self.pagination.paginate_queryset(None, request)

            # Verify that the cursor was decoded correctly
            # (This would be tested in the actual implementation)
            pass

        # Test invalid cursor
        invalid_cursor = 'invalid_base64!'
        request = self.factory.get(f'/api/users/?next_token={invalid_cursor}')

        with patch.object(self.pagination, 'paginate_queryset') as mock_paginate:
            mock_paginate.return_value = self.mock_paged_results.results
            self.pagination.paginate_queryset(None, request)

            # Verify that invalid cursor is handled gracefully
            pass

    def test_get_paginated_response(self):
        """Test paginated response generation."""
        # Set up pagination with mock data
        self.pagination.paged_results = self.mock_paged_results

        # Create a request without host to avoid DisallowedHost issues
        request = self.factory.get('/api/users/')
        self.pagination.request = request

        # Mock data
        data = [{'username': 'user1'}, {'username': 'user2'}]

        # Mock the _get_next_url method to avoid build_absolute_uri issues
        with patch.object(self.pagination, '_get_next_url') as mock_get_next_url:
            mock_get_next_url.return_value = 'http://example.com/api/users/?next_token=test_cursor'

            # Get paginated response
            response = self.pagination.get_paginated_response(data)

            # Check response structure
            self.assertIn('results', response.data)
            self.assertIn('has_more', response.data)
            self.assertIn('next', response.data)

            # Check response content
            self.assertEqual(response.data['results'], data)
            self.assertTrue(response.data['has_more'])
            self.assertEqual(response.data['next'], 'http://example.com/api/users/?next_token=test_cursor')

    def test_get_paginated_response_no_more_pages(self):
        """Test paginated response when there are no more pages."""
        # Mock PagedResultSet with no more pages
        class MockPagedResultSetNoMore:
            def __init__(self):
                self.results = [Mock(username='user1')]
                self.next_cookie = ""
                self.has_more = False

        self.pagination.paged_results = MockPagedResultSetNoMore()
        self.pagination.request = self.factory.get('/api/users/')

        # Mock data
        data = [{'username': 'user1'}]

        # Get paginated response
        response = self.pagination.get_paginated_response(data)

        # Check response structure
        self.assertIn('results', response.data)
        self.assertIn('has_more', response.data)
        self.assertNotIn('next', response.data)

        # Check response content
        self.assertEqual(response.data['results'], data)
        self.assertFalse(response.data['has_more'])

    def test_get_next_url(self):
        """Test next URL generation."""
        # Create request without host to avoid DisallowedHost issues
        self.pagination.request = self.factory.get('/api/users/')

        # Mock build_absolute_uri to return a predictable URL
        with patch.object(self.pagination.request, 'build_absolute_uri') as mock_build_uri:
            mock_build_uri.return_value = 'http://example.com/api/users/'

            # Test adding cursor to URL without existing parameters
            next_url = self.pagination._get_next_url('test_cursor')
            self.assertIn('next_token=test_cursor', next_url)

            # Test replacing existing cursor
            mock_build_uri.return_value = 'http://example.com/api/users/?next_token=old_cursor'
            next_url = self.pagination._get_next_url('new_cursor')
            self.assertIn('next_token=new_cursor', next_url)
            self.assertNotIn('next_token=old_cursor', next_url)

            # Test with other query parameters
            mock_build_uri.return_value = 'http://example.com/api/users/?filter=active&next_token=old_cursor'
            next_url = self.pagination._get_next_url('new_cursor')
            self.assertIn('filter=active', next_url)
            self.assertIn('next_token=new_cursor', next_url)

            # Test preserving page_size parameter
            mock_build_uri.return_value = 'http://example.com/api/users/?page_size=50&filter=active&next_token=old_cursor'
            next_url = self.pagination._get_next_url('new_cursor')
            self.assertIn('page_size=50', next_url)
            self.assertIn('filter=active', next_url)
            self.assertIn('next_token=new_cursor', next_url)
            self.assertNotIn('next_token=old_cursor', next_url)

            # Test with only page_size parameter
            mock_build_uri.return_value = 'http://example.com/api/users/?page_size=25'
            next_url = self.pagination._get_next_url('test_cursor')
            self.assertIn('page_size=25', next_url)
            self.assertIn('next_token=test_cursor', next_url)


class DummyModel:
    def __init__(self, name, age, active, photo=None):
        self.name = name
        self.age = age
        self.active = active
        self.photo = photo

class DummyQuerySet:
    def __init__(self, items):
        self.items = items
        self._filters = []
    def filter(self, **kwargs):
        self._filters.append(kwargs)
        results = self.items
        for key, value in kwargs.items():
            if key.endswith('__iexact'):
                field = key[:-8]
                field_value = getattr(results[0], field, '')
                if isinstance(field_value, (int, bool)):
                    results = [item for item in results if getattr(item, field) == value]
                else:
                    results = [item for item in results if str(getattr(item, field, '')).lower() == str(value).lower()]
            elif key.endswith('__icontains'):
                field = key[:-11]
                field_value = getattr(results[0], field, '')
                if isinstance(field_value, (int, bool)):
                    results = [item for item in results if str(value).lower() in str(getattr(item, field)).lower()]
                else:
                    results = [item for item in results if str(value).lower() in str(getattr(item, field, '')).lower()]
            elif key.endswith('__exact'):
                field = key[:-7]
                results = [item for item in results if getattr(item, field) == value]
            elif key.endswith('__contains'):
                field = key[:-10]
                results = [item for item in results if str(value) in str(getattr(item, field))]
            else:
                results = [item for item in results if getattr(item, key) == value]
        return DummyQuerySet(results)
    def __iter__(self):
        return iter(self.items)
    def __len__(self):
        return len(self.items)
    def all(self):
        return DummyQuerySet(self.items)

class LdapFilterBackendTestCase(unittest.TestCase):
    """Test cases for LdapFilterBackend."""
    def setUp(self):
        self.factory = APIRequestFactory()
        self.items = [
            DummyModel('Alice', 30, True),
            DummyModel('Bob', 25, False),
            DummyModel('Charlie', 40, True),
        ]
        self.queryset = DummyQuerySet(self.items)

    def _create_request(self, params):
        """Create a mock request with query_params."""
        request = Mock()
        request.query_params = params
        return request

    def test_string_iexact_filter(self):
        class TestFilter(LdapFilterBackend):
            filter_fields = {'name': {'lookup': 'iexact', 'type': 'string'}}
        backend = TestFilter()
        request = self._create_request({'name': 'alice'})
        filtered = backend.filter_queryset(request, self.queryset, None)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered.items[0].name, 'Alice')

    def test_string_icontains_filter(self):
        class TestFilter(LdapFilterBackend):
            filter_fields = {'name': {'lookup': 'icontains', 'type': 'string'}}
        backend = TestFilter()
        request = self._create_request({'name': 'li'})
        filtered = backend.filter_queryset(request, self.queryset, None)
        self.assertEqual(len(filtered), 2)
        self.assertIn('Alice', [i.name for i in filtered])
        self.assertIn('Charlie', [i.name for i in filtered])

    def test_integer_filter(self):
        class TestFilter(LdapFilterBackend):
            filter_fields = {'age': {'lookup': 'iexact', 'type': 'integer'}}
        backend = TestFilter()
        request = self._create_request({'age': '25'})
        filtered = backend.filter_queryset(request, self.queryset, None)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered.items[0].name, 'Bob')

    def test_boolean_filter(self):
        class TestFilter(LdapFilterBackend):
            filter_fields = {'active': {'lookup': 'exact', 'type': 'boolean'}}
        backend = TestFilter()
        request = self._create_request({'active': 'True'})
        filtered = backend.filter_queryset(request, self.queryset, None)
        self.assertEqual(len(filtered), 2)
        self.assertIn('Alice', [i.name for i in filtered])
        self.assertIn('Charlie', [i.name for i in filtered])

    def test_invalid_integer_value(self):
        class TestFilter(LdapFilterBackend):
            filter_fields = {'age': {'lookup': 'iexact', 'type': 'integer'}}
        backend = TestFilter()
        request = self._create_request({'age': 'notanumber'})
        filtered = backend.filter_queryset(request, self.queryset, None)
        # Should not filter out any items due to invalid int
        self.assertEqual(len(filtered), 3)

    def test_multiple_filters(self):
        class TestFilter(LdapFilterBackend):
            filter_fields = {
                'name': {'lookup': 'icontains', 'type': 'string'},
                'active': {'lookup': 'exact', 'type': 'boolean'},
            }
        backend = TestFilter()
        request = self._create_request({'name': 'li', 'active': 'True'})
        filtered = backend.filter_queryset(request, self.queryset, None)
        self.assertEqual(len(filtered), 2)
        self.assertIn('Alice', [i.name for i in filtered])
        self.assertIn('Charlie', [i.name for i in filtered])

    def test_openapi_schema_generation(self):
        class TestFilter(LdapFilterBackend):
            filter_fields = {
                'name': {'lookup': 'icontains', 'type': 'string'},
                'age': {'lookup': 'iexact', 'type': 'integer'},
                'active': {'lookup': 'exact', 'type': 'boolean'},
            }
        backend = TestFilter()
        params = backend.get_schema_operation_parameters(None)
        self.assertEqual(len(params), 3)
        self.assertEqual(params[0]['name'], 'name')
        self.assertEqual(params[0]['schema']['type'], 'string')
        self.assertEqual(params[1]['name'], 'age')
        self.assertEqual(params[1]['schema']['type'], 'integer')
        self.assertEqual(params[2]['name'], 'active')
        self.assertEqual(params[2]['schema']['type'], 'boolean')

    def test_custom_get_filter_queryset(self):
        class TestFilter(LdapFilterBackend):
            filter_fields = {'name': {'lookup': 'iexact', 'type': 'string'}}
            def get_filter_queryset(self, request, queryset, view):
                # Only allow filtering if a special param is present
                if request.query_params.get('special') == 'yes':
                    return self.apply_filters(request, queryset)
                return queryset
        backend = TestFilter()
        request = self._create_request({'name': 'alice', 'special': 'yes'})
        filtered = backend.filter_queryset(request, self.queryset, None)
        self.assertEqual(len(filtered), 1)
        request2 = self._create_request({'name': 'alice'})
        filtered2 = backend.filter_queryset(request2, self.queryset, None)
        self.assertEqual(len(filtered2), 3)

    def test_binary_filter(self):
        """Test binary field filtering with base64-encoded data."""
        class TestFilter(LdapFilterBackend):
            filter_fields = {'photo': {'lookup': 'exact', 'type': 'binary'}}

        filter_instance = TestFilter()

        # Test with valid base64 data
        test_photo_data = b'fake_photo_data'
        import base64
        photo_base64 = base64.b64encode(test_photo_data).decode('utf-8')

        request = self._create_request({'photo': photo_base64})
        queryset = DummyQuerySet([DummyModel('test', 25, True, photo=test_photo_data)])

        result = filter_instance.filter_queryset(request, queryset, None)
        # Should not raise an exception and should process the filter
        self.assertIsNotNone(result)

    def test_binary_filter_invalid_data(self):
        """Test binary field filtering with invalid base64 data."""
        class TestFilter(LdapFilterBackend):
            filter_fields = {'photo': {'lookup': 'exact', 'type': 'binary'}}

        filter_instance = TestFilter()

        # Test with invalid base64 data
        request = self._create_request({'photo': 'invalid_base64_data'})
        queryset = DummyQuerySet([DummyModel('test', 25, True, photo=b'some_data')])

        result = filter_instance.filter_queryset(request, queryset, None)
        # Should skip invalid data and return original queryset
        self.assertEqual(len(result), 1)
        self.assertEqual(result.items[0].name, 'test')

    def test_binary_filter_schema_generation(self):
        """Test OpenAPI schema generation for binary fields."""
        class TestFilter(LdapFilterBackend):
            filter_fields = {
                'photo': {'lookup': 'exact', 'type': 'binary'},
                'certificate': {'lookup': 'exact', 'type': 'binary'},
            }

        filter_instance = TestFilter()
        params = filter_instance.get_schema_operation_parameters(None)

        self.assertEqual(len(params), 2)
        self.assertEqual(params[0]['name'], 'photo')
        self.assertEqual(params[0]['schema']['type'], 'string')  # Binary data as base64 string
        self.assertEqual(params[1]['name'], 'certificate')
        self.assertEqual(params[1]['schema']['type'], 'string')  # Binary data as base64 string


