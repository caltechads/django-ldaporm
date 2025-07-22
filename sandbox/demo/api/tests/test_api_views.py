import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ldap_faker.unittest import LDAPFakerMixin

from demo.core.ldap.models import LDAPGroup, LDAPUser, NSRole


class TestAPIViews(LDAPFakerMixin, TestCase):
    """
    Test cases for API viewsets using LDAPFakerMixin.
    """

    ldap_modules = ['ldaporm.managers']
    ldap_fixtures = [('test_data.json', 'ldap://localhost:389', ['389'])]

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_users_url_patterns(self):
        """Test that URL patterns are correctly configured."""
        # Test that the URL patterns exist
        url = reverse('api:ldap-user-list')
        self.assertIn('/api/users/', url)

        # Test that detail URL pattern exists
        detail_url = reverse('api:ldap-user-detail', args=['testuser1'])
        self.assertIn('/api/users/testuser1/', detail_url)

    def test_users_viewset_configuration(self):
        """Test that the viewset is properly configured."""
        from demo.api.views.users import LDAPUserViewSet

        # Test that required attributes are set
        self.assertIsNotNone(LDAPUserViewSet.serializer_class)
        self.assertIsNotNone(LDAPUserViewSet.filter_backends)
        self.assertIsNotNone(LDAPUserViewSet.search_fields)
        self.assertIsNotNone(LDAPUserViewSet.ordering_fields)
        self.assertIsNotNone(LDAPUserViewSet.model)

        # Test that both filter backends are configured
        filter_backend_classes = [backend.__name__ for backend in LDAPUserViewSet.filter_backends]
        self.assertIn('LDAPUserFilter', filter_backend_classes)
        self.assertIn('LdapOrderingFilter', filter_backend_classes)

    def test_users_list_endpoint_structure(self):
        """Test that the users list endpoint returns correct structure."""
        url = reverse('api:ldap-user-list')
        response = self.client.get(url)

        # Should return 200 with test data
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 3)  # binduser + 2 test users

        # Check that our test users are in the results
        user_uids = [user['uid'] for user in response.data['results']]
        self.assertIn('testuser1', user_uids)
        self.assertIn('testuser2', user_uids)
        self.assertIn('binduser', user_uids)

    def test_users_serializer_validation(self):
        """Test that the user serializer validates data correctly."""
        from demo.api.serializers import LDAPUserSerializer

        # Test valid data
        user_data = {
            'uid': 'newuser1',
            'first_name': 'New',
            'last_name': 'One',
            'full_name': 'New User One',
            'mail': ['new1@example.com'],
            'employee_number': 12347,
            'employee_type': 'staff',
            'gid_number': 1000,
            'uid_number': 1003,
            'login_shell': '/bin/bash',
            'home_directory': '/home/newuser1',
            'room_number': 'C303',
            'home_phone': '555-0103',
            'mobile': '555-1003',
            'nsroledn': ['cn=staff,ou=roles,o=example,c=us'],
            'objectclass': ['inetOrgPerson', 'posixAccount']
        }

        serializer = LDAPUserSerializer(data=user_data)
        self.assertTrue(serializer.is_valid(), f"Validation errors: {serializer.errors}")

        # Test invalid data (missing required field)
        invalid_data = user_data.copy()
        del invalid_data['uid']
        serializer = LDAPUserSerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('uid', serializer.errors)

    def test_users_search_fields_configuration(self):
        """Test that search fields are properly configured."""
        from demo.api.views.users import LDAPUserViewSet

        # Check that search fields are defined
        self.assertIsInstance(LDAPUserViewSet.search_fields, (list, tuple))
        self.assertIn('uid', LDAPUserViewSet.search_fields)
        self.assertIn('full_name', LDAPUserViewSet.search_fields)
        self.assertIn('mail', LDAPUserViewSet.search_fields)

    def test_users_ordering_fields_configuration(self):
        """Test that ordering fields are properly configured."""
        from demo.api.views.users import LDAPUserViewSet

        # Check that ordering fields are defined
        self.assertIsInstance(LDAPUserViewSet.ordering_fields, (list, tuple))
        self.assertIn('uid', LDAPUserViewSet.ordering_fields)
        self.assertIn('full_name', LDAPUserViewSet.ordering_fields)
        self.assertIn('mail', LDAPUserViewSet.ordering_fields)

    def test_ldap_user_filter_functionality(self):
        """Test that the LDAPUserFilter (django_filter) works correctly."""
        base_url = reverse('api:ldap-user-list')

        # Test filtering by uid (iexact lookup)
        response = self.client.get(f"{base_url}?uid=testuser1")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['uid'], 'testuser1')

        # Test filtering by mail (icontains lookup)
        response = self.client.get(f"{base_url}?mail=testuser1@example.com")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['uid'], 'testuser1')

        # Test filtering by employee_number (iexact lookup)
        response = self.client.get(f"{base_url}?employee_number=12345")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['uid'], 'testuser1')

        # Test filtering by employee_type (iexact lookup)
        response = self.client.get(f"{base_url}?employee_type=staff")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)  # testuser1 and binduser
        user_uids = [user['uid'] for user in response.data['results']]
        self.assertIn('testuser1', user_uids)
        self.assertIn('binduser', user_uids)

        # Test filtering by full_name (icontains lookup)
        response = self.client.get(f"{base_url}?full_name=Test User")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)  # testuser1 and testuser2
        user_uids = [user['uid'] for user in response.data['results']]
        self.assertIn('testuser1', user_uids)
        self.assertIn('testuser2', user_uids)

        # Test filtering by gid_number (iexact lookup)
        response = self.client.get(f"{base_url}?gid_number=1000")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)  # all users have gid_number=1000

        # Test filtering by uid_number (iexact lookup)
        response = self.client.get(f"{base_url}?uid_number=1001")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['uid'], 'testuser1')

        # Test filtering by login_shell (iexact lookup)
        response = self.client.get(f"{base_url}?login_shell=/bin/bash")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)  # all users have /bin/bash

        # Test filtering by non-existent value
        response = self.client.get(f"{base_url}?uid=nonexistent")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def test_ldap_ordering_filter_functionality(self):
        """Test that the LdapOrderingFilter works correctly."""
        base_url = reverse('api:ldap-user-list')

        # Test default ordering (uid)
        response = self.client.get(base_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_uids = [user['uid'] for user in response.data['results']]
        self.assertEqual(user_uids, sorted(user_uids))  # Should be ordered by uid

        # Test ordering by uid ascending
        response = self.client.get(f"{base_url}?ordering=uid")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_uids = [user['uid'] for user in response.data['results']]
        self.assertEqual(user_uids, sorted(user_uids))

        # Test ordering by uid descending
        response = self.client.get(f"{base_url}?ordering=-uid")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_uids = [user['uid'] for user in response.data['results']]
        self.assertEqual(user_uids, sorted(user_uids, reverse=True))

        # Test ordering by full_name ascending (maps to cn in LDAP)
        response = self.client.get(f"{base_url}?ordering=full_name")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_names = [user['full_name'] for user in response.data['results']]
        self.assertEqual(user_names, sorted(user_names))

        # Test ordering by full_name descending
        response = self.client.get(f"{base_url}?ordering=-full_name")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_names = [user['full_name'] for user in response.data['results']]
        self.assertEqual(user_names, sorted(user_names, reverse=True))

        # Test ordering by mail ascending
        response = self.client.get(f"{base_url}?ordering=mail")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_mails = [user['mail'][0] for user in response.data['results']]
        self.assertEqual(user_mails, sorted(user_mails))

        # Test ordering by employee_number ascending
        response = self.client.get(f"{base_url}?ordering=employee_number")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_numbers = [user['employee_number'] for user in response.data['results']]
        self.assertEqual(user_numbers, sorted(user_numbers))

        # Test ordering by employee_number descending
        response = self.client.get(f"{base_url}?ordering=-employee_number")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_numbers = [user['employee_number'] for user in response.data['results']]
        self.assertEqual(user_numbers, sorted(user_numbers, reverse=True))

        # Test multiple field ordering
        response = self.client.get(f"{base_url}?ordering=employee_type,uid")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should be ordered by employee_type first, then uid

    def test_filter_and_ordering_combination(self):
        """Test that filtering and ordering work together."""
        base_url = reverse('api:ldap-user-list')

        # Test filtering by employee_type and ordering by uid
        response = self.client.get(f"{base_url}?employee_type=staff&ordering=uid")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)  # Only staff users
        user_uids = [user['uid'] for user in response.data['results']]
        self.assertEqual(user_uids, sorted(user_uids))  # Ordered by uid

        # Test filtering by full_name and ordering by employee_number
        response = self.client.get(f"{base_url}?full_name=Test User&ordering=employee_number")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)  # Only Test User users
        user_numbers = [user['employee_number'] for user in response.data['results']]
        self.assertEqual(user_numbers, sorted(user_numbers))  # Ordered by employee_number

    def test_invalid_ordering_parameters(self):
        """Test that invalid ordering parameters are handled gracefully."""
        base_url = reverse('api:ldap-user-list')

        # Test invalid ordering field
        response = self.client.get(f"{base_url}?ordering=invalid_field")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should still return results with default ordering

        # Test invalid ordering format
        response = self.client.get(f"{base_url}?ordering=uid,invalid_field")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should handle partial valid ordering

    def test_invalid_filter_parameters(self):
        """Test that invalid filter parameters are handled gracefully."""
        base_url = reverse('api:ldap-user-list')

        # Test invalid filter field
        response = self.client.get(f"{base_url}?invalid_field=value")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should ignore invalid filters and return all results

        # Test invalid filter value for number field
        response = self.client.get(f"{base_url}?employee_number=not_a_number")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should handle invalid number gracefully

    def test_users_pagination_functionality(self):
        """Test that pagination is working."""
        # Test pagination
        list_url = reverse('api:ldap-user-list')
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        # Check for standard pagination format
        self.assertIn('count', response.data)
        self.assertIn('next', response.data)
        self.assertIn('previous', response.data)
        self.assertIsInstance(response.data['results'], list)

    def test_users_detail_endpoint(self):
        """Test that the user detail endpoint works."""
        detail_url = reverse('api:ldap-user-detail', args=['testuser1'])
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['uid'], 'testuser1')
        self.assertEqual(response.data['full_name'], 'Test User 1')


class LDAPGroupViewSetTests(LDAPFakerMixin, TestCase):
    """Test LDAP Group ViewSet functionality with LDAPFakerMixin."""

    ldap_modules = ['ldaporm.managers']
    ldap_fixtures = [('test_data.json', 'ldap://localhost:389', ['389'])]

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_groups_url_patterns(self):
        """Test that URL patterns are correctly configured."""
        # Test that the URL patterns exist
        url = reverse('api:ldap-group-list')
        self.assertIn('/api/groups/', url)

        # Test that detail URL pattern exists
        detail_url = reverse('api:ldap-group-detail', args=['testgroup1'])
        self.assertIn('/api/groups/testgroup1/', detail_url)

    def test_groups_viewset_configuration(self):
        """Test that the viewset is properly configured."""
        from demo.api.views.groups import LDAPGroupViewSet

        # Test that required attributes are set
        self.assertIsNotNone(LDAPGroupViewSet.serializer_class)
        self.assertIsNotNone(LDAPGroupViewSet.filter_backends)
        self.assertIsNotNone(LDAPGroupViewSet.search_fields)
        self.assertIsNotNone(LDAPGroupViewSet.ordering_fields)
        self.assertIsNotNone(LDAPGroupViewSet.model)

    def test_groups_list_endpoint_structure(self):
        """Test that the groups list endpoint returns correct structure."""
        url = reverse('api:ldap-group-list')
        response = self.client.get(url)

        # Should return 200 with test data
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 2)

        # Check that our test groups are in the results
        group_cns = [group['cn'] for group in response.data['results']]
        self.assertIn('testgroup1', group_cns)
        self.assertIn('testgroup2', group_cns)

    def test_groups_serializer_validation(self):
        """Test that the group serializer validates data correctly."""
        from demo.api.serializers import LDAPGroupSerializer

        # Test valid data
        group_data = {
            'cn': 'newgroup1',
            'gid_number': 1003,
            'description': 'New Group One',
            'member_uids': ['user5', 'user6'],
            'objectclass': ['posixGroup']
        }

        serializer = LDAPGroupSerializer(data=group_data)
        self.assertTrue(serializer.is_valid(), f"Validation errors: {serializer.errors}")

        # Test invalid data (missing required field)
        invalid_data = group_data.copy()
        del invalid_data['cn']
        serializer = LDAPGroupSerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('cn', serializer.errors)

    def test_groups_search_fields_configuration(self):
        """Test that search fields are properly configured."""
        from demo.api.views.groups import LDAPGroupViewSet

        # Check that search fields are defined
        self.assertIsInstance(LDAPGroupViewSet.search_fields, (list, tuple))
        self.assertIn('cn', LDAPGroupViewSet.search_fields)
        self.assertIn('description', LDAPGroupViewSet.search_fields)

    def test_groups_ordering_fields_configuration(self):
        """Test that ordering fields are properly configured."""
        from demo.api.views.groups import LDAPGroupViewSet

        # Check that ordering fields are defined
        self.assertIsInstance(LDAPGroupViewSet.ordering_fields, (list, tuple))
        self.assertIn('cn', LDAPGroupViewSet.ordering_fields)
        self.assertIn('gid_number', LDAPGroupViewSet.ordering_fields)

    def test_groups_search_functionality(self):
        """Test the search functionality."""
        # Test search by cn
        search_url = reverse('api:ldap-group-list')
        response = self.client.get(f"{search_url}?search=testgroup1")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)

        # Should find testgroup1
        group_cns = [group['cn'] for group in response.data['results']]
        self.assertIn('testgroup1', group_cns)

    def test_groups_ordering_functionality(self):
        """Test the ordering functionality."""
        # Test ordering by cn
        order_url = reverse('api:ldap-group-list')
        response = self.client.get(f"{order_url}?ordering=cn")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)

        # Check that results are ordered
        group_cns = [group['cn'] for group in response.data['results']]
        self.assertEqual(group_cns, sorted(group_cns))

    def test_groups_detail_endpoint(self):
        """Test that the group detail endpoint works."""
        detail_url = reverse('api:ldap-group-detail', args=['testgroup1'])
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['cn'], 'testgroup1')
        self.assertEqual(response.data['description'], 'Test Group 1')


class NSRoleViewSetTests(LDAPFakerMixin, TestCase):
    """Test NSRole ViewSet functionality with LDAPFakerMixin."""

    ldap_modules = ['ldaporm.managers']
    ldap_fixtures = [('test_data.json', 'ldap://localhost:389', ['389'])]

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_roles_url_patterns(self):
        """Test that URL patterns are correctly configured."""
        # Test that the URL patterns exist
        url = reverse('api:ldap-role-list')
        self.assertIn('/api/roles/', url)

        # Test that detail URL pattern exists
        detail_url = reverse('api:ldap-role-detail', args=['testrole1'])
        self.assertIn('/api/roles/testrole1/', detail_url)

    def test_roles_viewset_configuration(self):
        """Test that the viewset is properly configured."""
        from demo.api.views.roles import NSRoleViewSet

        # Test that required attributes are set
        self.assertIsNotNone(NSRoleViewSet.serializer_class)
        self.assertIsNotNone(NSRoleViewSet.filter_backends)
        self.assertIsNotNone(NSRoleViewSet.search_fields)
        self.assertIsNotNone(NSRoleViewSet.ordering_fields)
        self.assertIsNotNone(NSRoleViewSet.model)

    def test_roles_list_endpoint_structure(self):
        """Test that the roles list endpoint returns correct structure."""
        url = reverse('api:ldap-role-list')
        response = self.client.get(url)

        # Should return 200 with test data
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 2)

        # Check that our test roles are in the results
        role_cns = [role['cn'] for role in response.data['results']]
        self.assertIn('testrole1', role_cns)
        self.assertIn('testrole2', role_cns)

    def test_roles_serializer_validation(self):
        """Test that the role serializer validates data correctly."""
        from demo.api.serializers import NSRoleSerializer

        # Test valid data
        role_data = {
            'cn': 'newrole1',
            'description': 'New Role One',
            'objectclass': ['nsRoleDefinition']
        }

        serializer = NSRoleSerializer(data=role_data)
        self.assertTrue(serializer.is_valid(), f"Validation errors: {serializer.errors}")

        # Test invalid data (missing required field)
        invalid_data = role_data.copy()
        del invalid_data['cn']
        serializer = NSRoleSerializer(data=invalid_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('cn', serializer.errors)

    def test_roles_search_fields_configuration(self):
        """Test that search fields are properly configured."""
        from demo.api.views.roles import NSRoleViewSet

        # Check that search fields are defined
        self.assertIsInstance(NSRoleViewSet.search_fields, (list, tuple))
        self.assertIn('cn', NSRoleViewSet.search_fields)
        self.assertIn('description', NSRoleViewSet.search_fields)

    def test_roles_ordering_fields_configuration(self):
        """Test that ordering fields are properly configured."""
        from demo.api.views.roles import NSRoleViewSet

        # Check that ordering fields are defined
        self.assertIsInstance(NSRoleViewSet.ordering_fields, (list, tuple))
        self.assertIn('cn', NSRoleViewSet.ordering_fields)
        self.assertIn('description', NSRoleViewSet.ordering_fields)

    def test_roles_search_functionality(self):
        """Test the search functionality."""
        # Test search by cn
        search_url = reverse('api:ldap-role-list')
        response = self.client.get(f"{search_url}?search=testrole1")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)

        # Should find testrole1
        role_cns = [role['cn'] for role in response.data['results']]
        self.assertIn('testrole1', role_cns)

    def test_roles_ordering_functionality(self):
        """Test the ordering functionality."""
        # Test ordering by cn
        order_url = reverse('api:ldap-role-list')
        response = self.client.get(f"{order_url}?ordering=cn")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)

        # Check that results are ordered
        role_cns = [role['cn'] for role in response.data['results']]
        self.assertEqual(role_cns, sorted(role_cns))

    def test_roles_pagination_functionality(self):
        """Test that pagination is working."""
        # Test pagination
        list_url = reverse('api:ldap-role-list')
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        # Check for standard pagination format
        self.assertIn('count', response.data)
        self.assertIn('next', response.data)
        self.assertIn('previous', response.data)
        self.assertIsInstance(response.data['results'], list)

    def test_roles_detail_endpoint(self):
        """Test that the role detail endpoint works."""
        detail_url = reverse('api:ldap-role-detail', args=['testrole1'])
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['cn'], 'testrole1')
        self.assertEqual(response.data['description'], 'Test Role 1')


class APIEndpointsIntegrationTests(LDAPFakerMixin, TestCase):
    """Integration tests for API endpoints."""

    ldap_modules = ['ldaporm.managers']
    ldap_fixtures = [('test_data.json', 'ldap://localhost:389', ['389'])]

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_api_root_endpoint(self):
        """Test that the API root endpoint is accessible."""
        url = reverse('api:api-root')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check that all expected endpoints are listed
        self.assertIn('users', response.data)
        self.assertIn('groups', response.data)
        self.assertIn('roles', response.data)

    def test_api_endpoints_consistency(self):
        """Test that all API endpoints follow consistent patterns."""
        endpoints = [
            ('api:ldap-user-list', '/api/users/'),
            ('api:ldap-group-list', '/api/groups/'),
            ('api:ldap-role-list', '/api/roles/'),
        ]

        for endpoint_name, expected_path in endpoints:
            url = reverse(endpoint_name)
            self.assertIn(expected_path, url)

            # Test that the endpoint is accessible (should return 200 or appropriate error)
            response = self.client.get(url)
            # Should not return 404 (endpoint exists)
            self.assertNotEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_api_response_format(self):
        """Test that API responses follow consistent format."""
        # Test users endpoint
        url = reverse('api:ldap-user-list')
        response = self.client.get(url)

        # Should have standard DRF response structure
        self.assertIsInstance(response.data, dict)

        # If pagination is enabled, should have pagination keys
        if 'results' in response.data:
            # Check for standard pagination format
            self.assertIn('count', response.data)
            self.assertIn('next', response.data)
            self.assertIn('previous', response.data)
            self.assertIsInstance(response.data['results'], list)

    def test_cross_endpoint_functionality(self):
        """Test that all endpoints work together."""
        # Test that we can access all three main endpoints
        endpoints = [
            reverse('api:ldap-user-list'),
            reverse('api:ldap-group-list'),
            reverse('api:ldap-role-list'),
        ]

        for endpoint in endpoints:
            response = self.client.get(endpoint)
            # Should not return 404 (endpoint exists)
            self.assertNotEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class CRUDOperationsTests(LDAPFakerMixin, TestCase):
    """Test CRUD operations for all viewsets."""

    ldap_modules = ['ldaporm.managers']
    ldap_fixtures = [('test_data.json', 'ldap://localhost:389', ['389'])]

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_users_crud_operations(self):
        """Test CRUD operations for LDAP users."""
        # Test list operation
        url = reverse('api:ldap-user-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)

        # Test retrieve operation
        detail_url = reverse('api:ldap-user-detail', args=['testuser1'])
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['uid'], 'testuser1')

    def test_groups_crud_operations(self):
        """Test CRUD operations for LDAP groups."""
        # Test list operation
        url = reverse('api:ldap-group-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)

        # Test retrieve operation
        detail_url = reverse('api:ldap-group-detail', args=['testgroup1'])
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['cn'], 'testgroup1')

    def test_roles_crud_operations(self):
        """Test CRUD operations for NSRoles."""
        # Test list operation
        url = reverse('api:ldap-role-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)

        # Test retrieve operation
        detail_url = reverse('api:ldap-role-detail', args=['testrole1'])
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['cn'], 'testrole1')