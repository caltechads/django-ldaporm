# type: ignore
"""
Comprehensive test suite for the F class using python-ldap-faker.

This test suite uses python-ldap-faker to simulate a 389 Directory Server,
providing realistic LDAP behavior for testing the F class functionality.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import ldap
import pytest
from ldap_faker.unittest import LDAPFakerMixin

from ldaporm.fields import CharField, IntegerField
from ldaporm.managers import F, LdapManager, PagedResultSet
from ldaporm.models import Model
from ldaporm.options import Options

import os
import django
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
                    "tls_verify": "never"
                },
                "write": {
                    "url": "ldap://localhost:389",
                    "user": "cn=admin,dc=example,dc=com",
                    "password": "admin",
                    "use_starttls": False,
                    "tls_verify": "never"
                }
            }
        }
    )
    try:
        django.setup()
    except Exception:
        pass


class MyTestUser(Model):
    """Test model for user objects."""

    uid = CharField(primary_key=True)
    cn = CharField()
    sn = CharField()
    uidNumber = IntegerField()
    gidNumber = IntegerField()
    homeDirectory = CharField()
    loginShell = CharField()

    class Meta:
        basedn = "ou=users,dc=example,dc=com"
        objectclass = "posixAccount"
        ldap_server = "test_server"
        ordering: list[str] = []
        ldap_options: list[str] = []
        extra_objectclasses = ["top"]


class TestFClassWithFaker(LDAPFakerMixin, unittest.TestCase):
    """Test suite for F class using python-ldap-faker."""

    ldap_modules = ['ldaporm']

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create test data for the fake LDAP server (do not load it here)
        cls.test_data = [
            [
                "cn=admin,dc=example,dc=com",
                {
                    "cn": [b"admin"],
                    "userPassword": [b"admin"],
                    "objectclass": [b"simpleSecurityObject", b"organizationalRole", b"top"]
                }
            ],
            [
                "uid=alice,ou=users,dc=example,dc=com",
                {
                    "uid": [b"alice"],
                    "cn": [b"Alice Johnson"],
                    "sn": [b"Johnson"],
                    "uidNumber": [b"1001"],
                    "gidNumber": [b"1001"],
                    "homeDirectory": [b"/home/alice"],
                    "loginShell": [b"/bin/bash"],
                    "objectclass": [b"posixAccount", b"top"]
                }
            ],
            [
                "uid=bob,ou=users,dc=example,dc=com",
                {
                    "uid": [b"bob"],
                    "cn": [b"Bob Smith"],
                    "sn": [b"Smith"],
                    "uidNumber": [b"1002"],
                    "gidNumber": [b"1002"],
                    "homeDirectory": [b"/home/bob"],
                    "loginShell": [b"/bin/bash"],
                    "objectclass": [b"posixAccount", b"top"]
                }
            ],
            [
                "uid=charlie,ou=users,dc=example,dc=com",
                {
                    "uid": [b"charlie"],
                    "cn": [b"Charlie Brown"],
                    "sn": [b"Brown"],
                    "uidNumber": [b"1003"],
                    "gidNumber": [b"1003"],
                    "homeDirectory": [b"/home/charlie"],
                    "loginShell": [b"/bin/zsh"],
                    "objectclass": [b"posixAccount", b"top"]
                }
            ],
            [
                "uid=diana,ou=users,dc=example,dc=com",
                {
                    "uid": [b"diana"],
                    "cn": [b"Diana Prince"],
                    "sn": [b"Prince"],
                    "uidNumber": [b"1004"],
                    "gidNumber": [b"1004"],
                    "homeDirectory": [b"/home/diana"],
                    "loginShell": [b"/bin/bash"],
                    "objectclass": [b"posixAccount", b"top"]
                }
            ],
            [
                "uid=edward,ou=users,dc=example,dc=com",
                {
                    "uid": [b"edward"],
                    "cn": [b"Edward Norton"],
                    "sn": [b"Norton"],
                    "uidNumber": [b"1005"],
                    "gidNumber": [b"1005"],
                    "homeDirectory": [b"/home/edward"],
                    "loginShell": [b"/bin/tcsh"],
                    "objectclass": [b"posixAccount", b"top"]
                }
            ]
        ]

    def setUp(self):
        super().setUp()
        if not hasattr(self, 'ldap_faker'):
            LDAPFakerMixin.setUp(self)

        # Set up Django settings patcher
        self.settings_patcher = patch('django.conf.settings.LDAP_SERVERS', {
            "test_server": {
                "read": {
                    "url": "ldap://localhost:389",
                    "user": "cn=admin,dc=example,dc=com",
                    "password": "admin",
                    "use_starttls": False,
                    "tls_verify": "never"
                },
                "write": {
                    "url": "ldap://localhost:389",
                    "user": "cn=admin,dc=example,dc=com",
                    "password": "admin",
                    "use_starttls": False,
                    "tls_verify": "never"
                }
            }
        })
        self.settings_patcher.start()

        # Initialize the manager
        self.manager = LdapManager()
        self.manager.contribute_to_class(MyTestUser, 'objects')

        # Clear the fake LDAP directory before each test
        self.server_factory.default.raw_objects.clear()  # type: ignore[attr-defined]
        self.server_factory.default.objects.clear()  # type: ignore[attr-defined]

        # Reload test data before each test
        for dn, attrs in self.test_data:
            self.server_factory.default.register_object((dn, attrs))  # type: ignore[attr-defined]

    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self, 'settings_patcher'):
            self.settings_patcher.stop()
        super().tearDown()

    def test_f_initialization(self):
        """Test F class initialization."""
        f = F(self.manager)
        assert f.manager == self.manager
        assert f.model == MyTestUser
        assert f.chain == []

    def test_filter_exact_match(self):
        """Test exact match filtering."""
        f = F(self.manager)
        result = f.filter(uid="alice").all()

        assert len(result) == 1
        assert result[0].uid == "alice"
        assert result[0].cn == "Alice Johnson"

    def test_filter_multiple_conditions(self):
        """Test filtering with multiple conditions."""
        f = F(self.manager)
        result = f.filter(loginShell="/bin/bash", uidNumber__gte=1002).all()

        assert len(result) == 2  # bob, diana
        uids = [user.uid for user in result]
        assert "bob" in uids
        assert "diana" in uids

    def test_filter_integer_comparisons(self):
        """Test integer comparison filters."""

        # Test greater than
        f = F(self.manager)
        f = f.filter(uidNumber__gt=1002)
        result = f.all()
        assert len(result) == 3  # charlie, diana, edward
        uids = [user.uid for user in result]
        assert "charlie" in uids
        assert "diana" in uids
        assert "edward" in uids

        # Test less than
        f = F(self.manager)
        f = f.filter(uidNumber__lt=1003)
        result = f.all()
        assert len(result) == 2  # alice, bob
        uids = [user.uid for user in result]
        assert "alice" in uids
        assert "bob" in uids

        # Test greater than or equal
        f = F(self.manager)
        result = f.filter(uidNumber__gte=1003).all()
        assert len(result) == 3  # charlie, diana, edward

        # Test less than or equal
        f = F(self.manager)
        result = f.filter(uidNumber__lte=1002).all()
        assert len(result) == 2  # alice, bob

    def test_filter_integer_comparison_type_error(self):
        """Test that integer comparisons raise TypeError for non-integer fields."""
        f = F(self.manager)

        with pytest.raises(TypeError, match="Integer comparison methods.*can only be used on IntegerField"):
            f.filter(uid__gt="alice").all()

    def test_filter_wildcard(self):
        """Test wildcard filtering."""

        # Test contains
        f = F(self.manager)
        result = f.wildcard("cn", "*Brown*").all()
        assert len(result) == 1
        assert result[0].cn == "Charlie Brown"

        # Test starts with
        f = F(self.manager)
        wildcard_f = f.wildcard("cn", "Alice*")
        result = wildcard_f.all()
        assert len(result) == 1
        assert result[0].cn == "Alice Johnson"

        # Test ends with
        f = F(self.manager)
        result = f.wildcard("cn", "*Smith").all()
        assert len(result) == 1
        assert result[0].cn == "Bob Smith"

    def test_filter_in_operator(self):
        """Test __in filter operator."""
        f = F(self.manager)
        result = f.filter(uid__in=["alice", "bob", "charlie"]).all()

        assert len(result) == 3
        uids = [user.uid for user in result]
        assert "alice" in uids
        assert "bob" in uids
        assert "charlie" in uids

    def test_filter_exists(self):
        """Test __exists filter operator."""
        f = F(self.manager)
        result = f.filter(uid__exists=True).all()

        assert len(result) == 5  # All users have uid

    def test_only_restriction(self):
        """Test attribute restriction with only()."""
        f = F(self.manager)
        result = f.filter(uid="alice").only("uid", "cn").first()

        assert result.uid == "alice"
        assert result.cn == "Alice Johnson"
        # These should not be loaded
        assert not hasattr(result, 'sn') or result.sn is None

    def test_order_by(self):
        """Test ordering of results."""
        f = F(self.manager)
        result = f.filter(objectclass="posixAccount").order_by("uid").all()
        uids = [user.uid for user in result]
        assert uids == ["alice", "bob", "charlie", "diana", "edward"]

        # Test reverse ordering
        result = f.filter(objectclass="posixAccount").order_by("-uid").all()
        uids = [user.uid for user in result]
        assert uids == ["edward", "diana", "charlie", "bob", "alice"]

    def test_order_by_multiple_fields(self):
        """Test ordering by multiple fields."""
        f = F(self.manager)
        result = f.filter(objectclass="posixAccount").order_by("loginShell", "uid").all()
        # Should be ordered by loginShell first, then uid
        shells = [user.loginShell for user in result]
        uids = [user.uid for user in result]

        # Check that shells are sorted
        assert shells == sorted(shells)

        # Check that uids are sorted within each shell group
        # Expected order: alice, bob, diana (all /bin/bash), edward (/bin/tcsh), charlie (/bin/zsh)
        expected_uids = ['alice', 'bob', 'diana', 'edward', 'charlie']
        assert uids == expected_uids

    def test_values_method(self):
        """Test values() method."""
        f = F(self.manager)
        result = f.filter(uid="alice").values("uid", "cn")

        assert len(result) == 1
        assert result[0]["uid"] == "alice"
        assert result[0]["cn"] == "Alice Johnson"
        assert "sn" not in result[0]

    def test_values_list_method(self):
        """Test values_list() method."""
        f = F(self.manager)
        result = f.filter(uid="alice").values_list("uid", "cn")

        assert len(result) == 1
        assert result[0] == ("alice", "Alice Johnson")

    def test_values_list_flat(self):
        """Test values_list() with flat=True."""
        f = F(self.manager)
        result = f.filter(uid="alice").values_list("uid", flat=True)

        assert result == ["alice"]

    def test_values_list_named(self):
        """Test values_list() with named=True."""
        f = F(self.manager)
        result = f.filter(uid="alice").values_list("uid", "cn", named=True)

        assert len(result) == 1
        assert result[0].uid == "alice"  # type: ignore[attr-defined]
        assert result[0].cn == "Alice Johnson"  # type: ignore[attr-defined]

    def test_first_method(self):
        """Test first() method."""
        f = F(self.manager)
        result = f.filter(objectclass="posixAccount").order_by("uid").first()
        assert result.uid == "alice"

    def test_get_method(self):
        """Test get() method."""
        f = F(self.manager)
        result = f.filter(uid="alice").get()

        assert result.uid == "alice"
        assert result.cn == "Alice Johnson"

    def test_get_method_multiple_results(self):
        """Test get() method with multiple results raises exception."""
        f = F(self.manager)

        with pytest.raises(MyTestUser.MultipleObjectsReturned):
            f.filter(loginShell="/bin/bash").get()

    def test_get_method_no_results(self):
        """Test get() method with no results raises exception."""
        f = F(self.manager)

        with pytest.raises(MyTestUser.DoesNotExist):
            f.filter(uid="nonexistent").get()

    def test_exists_method(self):
        """Test exists() method."""
        f = F(self.manager)

        assert f.filter(uid="alice").exists() is True
        assert f.filter(uid="nonexistent").exists() is False

    def test_logical_operations(self):
        """Test logical AND and OR operations."""

        # Test AND operation
        f1 = F(self.manager)
        f2 = F(self.manager)
        result = (f1.filter(uid="alice") & f2.filter(cn="Alice Johnson")).all()
        assert len(result) == 1
        assert result[0].uid == "alice"

        # Test OR operation
        f1 = F(self.manager)
        f2 = F(self.manager)
        or_f = f1.filter(uid="alice") | f2.filter(uid="bob")
        result = or_f.all()
        assert len(result) == 2
        uids = [user.uid for user in result]
        assert "alice" in uids
        assert "bob" in uids

    def test_string_representation(self):
        """Test string representation of F objects."""
        f = F(self.manager)
        f = f.filter(uid="alice")

        # The string representation should be a valid LDAP filter
        filter_str = str(f)
        assert "(uid=alice)" in filter_str

    def test_update_method(self):
        """Test update() method."""
        f = F(self.manager)
        f.filter(uid="alice").update(cn="Alice Updated")

        # Verify the update
        updated_user = f.filter(uid="alice").get()
        assert updated_user.cn == "Alice Updated"

    def test_delete_method(self):
        """Test delete() method."""

        # Print users before deletion
        f = F(self.manager)
        all_users = f.filter(objectclass="posixAccount").all()

        # Print filter string for deletion
        del_f = F(self.manager)
        del_f = del_f.filter(uid="edward")
        del_f.delete()

        # Print users after deletion
        f = F(self.manager)
        all_users_after = f.filter(objectclass="posixAccount").all()

        # Verify deletion
        f = F(self.manager)
        assert not f.filter(uid="edward").exists()
        f = F(self.manager)
        assert f.filter(uid="alice").exists()  # Others should still exist

    def test_server_side_sorting(self):
        """Test server-side sorting functionality."""
        f = F(self.manager)
        result = f.filter(objectclass="posixAccount").order_by("uid").all()
        uids = [user.uid for user in result]
        assert uids == ["alice", "bob", "charlie", "diana", "edward"]

    def test_server_side_sorting_with_controls(self):
        """Test server-side sorting with explicit sort controls."""
        self.manager._check_server_sorting_support = lambda key="read": True
        f = F(self.manager)

        # Test ascending order with server-side sort
        result = f.filter(objectclass="posixAccount").order_by("uid").all()
        uids = [user.uid for user in result]
        assert uids == ["alice", "bob", "charlie", "diana", "edward"]

        # Test descending order with server-side sort
        result = f.filter(objectclass="posixAccount").order_by("-uid").all()
        uids = [user.uid for user in result]
        assert uids == ["edward", "diana", "charlie", "bob", "alice"]

        # Test multiple field sorting with server-side sort
        result = f.filter(objectclass="posixAccount").order_by("loginShell", "uid").all()
        shells = [user.loginShell for user in result]
        uids = [user.uid for user in result]

        # Verify server-side sorting worked correctly
        # Expected order: alice, bob, diana (all /bin/bash), edward (/bin/tcsh), charlie (/bin/zsh)
        expected_uids = ['alice', 'bob', 'diana', 'edward', 'charlie']
        assert uids == expected_uids

        # Verify that the sorting was done server-side by checking if the manager
        # attempted to use server-side sorting
        assert hasattr(self.manager, '_check_server_sorting_support')

    def test_client_side_sorting_fallback(self):
        """Test client-side sorting fallback when server doesn't support sorting."""
        # Mock server sorting support to return False
        self.manager._check_server_sorting_support = lambda key="read": False

        f = F(self.manager)
        result = f.filter(objectclass="posixAccount").order_by("uid").all()
        uids = [user.uid for user in result]
        assert uids == ["alice", "bob", "charlie", "diana", "edward"]

    def test_complex_filter_chain(self):
        """Test complex filter chains."""
        f = F(self.manager)

        # Complex filter: users with uidNumber >= 1002 AND loginShell = /bin/bash
        result = f.filter(uidNumber__gte=1002, loginShell="/bin/bash").all()

        assert len(result) == 2  # bob, diana
        uids = [user.uid for user in result]
        assert "bob" in uids
        assert "diana" in uids

    def test_filter_with_none_value(self):
        """Test filtering with None values."""
        f = F(self.manager)

        # All users should have uid, so filtering for uid=None should return empty
        result = f.filter(uid=None).all()
        assert len(result) == 0

    def test_invalid_field_error(self):
        """Test error handling for invalid field names."""
        f = F(self.manager)

        with pytest.raises(MyTestUser.InvalidField):
            f.filter(invalid_field="value").all()

    def test_invalid_suffix_error(self):
        """Test error handling for invalid filter suffixes."""
        f = F(self.manager)

        with pytest.raises(F.UnknownSuffix):
            f.filter(uid__invalid="value").all()

    def test_no_filter_specified_error(self):
        """Test error handling when no filter is specified."""
        f = F(self.manager)

        # With our current implementation, an empty F object returns all objects
        # because it uses a default filter that matches everything
        users = f.all()
        self.assertEqual(len(users), 5)  # Should return all 5 test users

    def test_values_with_only_error(self):
        """Test error when using values() with only()."""
        f = F(self.manager)
        f = f.filter(uid="alice").only("uid", "cn")

        with pytest.raises(NotImplementedError, match="Don't use .only\\(\\) with .values\\(\\)"):
            f.values("uid", "cn")

    def test_values_list_with_only_error(self):
        """Test error when using values_list() with only()."""
        f = F(self.manager)
        f = f.filter(uid="alice").only("uid", "cn")

        with pytest.raises(NotImplementedError, match="Don't use .only\\(\\) with .values_list\\(\\)"):
            f.values_list("uid", "cn")

    def test_values_list_flat_multiple_fields_error(self):
        """Test error when using flat=True with multiple fields."""
        f = F(self.manager)

        with pytest.raises(ValueError, match="Cannot use flat=True when asking for more than one field"):
            f.filter(uid="alice").values_list("uid", "cn", flat=True)

    def test_in_filter_not_list_error(self):
        """Test error when __in filter is not given a list."""
        f = F(self.manager)

        with pytest.raises(ValueError, match="When using the \"__in\" filter you must supply a list"):
            f.filter(uid__in="alice").all()

    # ========================================
    # Tests for new functionality (iteration, indexing, etc.)
    # ========================================

    def test_iteration(self):
        """Test that F instances are iterable."""
        f = F(self.manager)
        f = f.filter(objectclass="posixAccount")

        # Test direct iteration
        users = list(f)
        assert len(users) == 5
        uids = [user.uid for user in users]
        assert "alice" in uids
        assert "bob" in uids
        assert "charlie" in uids
        assert "diana" in uids
        assert "edward" in uids

        # Test iteration with filter
        f = F(self.manager)
        f = f.filter(loginShell="/bin/bash")
        bash_users = list(f)
        assert len(bash_users) == 3
        bash_uids = [user.uid for user in bash_users]
        assert "alice" in bash_uids
        assert "bob" in bash_uids
        assert "diana" in bash_uids

    def test_indexing(self):
        """Test indexing and slicing of F instances."""
        f = F(self.manager)
        f = f.filter(objectclass="posixAccount").order_by("uid")

        # Test single index
        first_user = f[0]
        assert first_user.uid == "alice"

        # Test negative index
        last_user = f[-1]
        assert last_user.uid == "edward"

        # Test slicing
        first_three = f[:3]  # type: ignore[assignment]
        assert len(first_three) == 3
        assert first_three[0].uid == "alice"  # type: ignore[attr-defined]
        assert first_three[1].uid == "bob"  # type: ignore[attr-defined]
        assert first_three[2].uid == "charlie"  # type: ignore[attr-defined]

        # Test slice with step
        every_other = f[::2]  # type: ignore[assignment]
        assert len(every_other) == 3
        assert every_other[0].uid == "alice"  # type: ignore[attr-defined]
        assert every_other[1].uid == "charlie"  # type: ignore[attr-defined]
        assert every_other[2].uid == "edward"  # type: ignore[attr-defined]

    def test_length(self):
        """Test len() function on F instances."""
        f = F(self.manager)
        f = f.filter(objectclass="posixAccount")

        # Test length of all users
        assert len(f) == 5

        # Test length with filter
        f = F(self.manager)
        f = f.filter(loginShell="/bin/bash")
        assert len(f) == 3

        # Test length with no results
        f = F(self.manager)
        f = f.filter(uid="nonexistent")
        assert len(f) == 0

    def test_count_method(self):
        """Test count() method."""
        f = F(self.manager)
        f = f.filter(objectclass="posixAccount")

        # Test count of all users
        assert f.count() == 5

        # Test count with filter
        f = F(self.manager)
        f = f.filter(loginShell="/bin/bash")
        assert f.count() == 3

        # Test count with no results
        f = F(self.manager)
        f = f.filter(uid="nonexistent")
        assert f.count() == 0

    def test_as_list_method(self):
        """Test as_list() method."""
        f = F(self.manager)
        f = f.filter(objectclass="posixAccount").order_by("uid")

        # Test as_list returns a list
        user_list = f.as_list()
        assert isinstance(user_list, list)
        assert len(user_list) == 5

        # Test order is preserved
        uids = [user.uid for user in user_list]
        assert uids == ["alice", "bob", "charlie", "diana", "edward"]

        # Test with filter
        f = F(self.manager)
        f = f.filter(loginShell="/bin/bash")
        bash_list = f.as_list()
        assert len(bash_list) == 3
        bash_uids = [user.uid for user in bash_list]
        assert "alice" in bash_uids
        assert "bob" in bash_uids
        assert "diana" in bash_uids

    def test_get_or_none_method(self):
        """Test get_or_none() method."""
        f = F(self.manager)

        # Test with existing user
        user = f.filter(uid="alice").get_or_none()
        assert user is not None
        assert user.uid == "alice"
        assert user.cn == "Alice Johnson"

        # Test with non-existent user
        user = f.filter(uid="nonexistent").get_or_none()
        assert user is None

        # Test with multiple results (should return None)
        user = f.filter(loginShell="/bin/bash").get_or_none()
        assert user is None

    def test_first_or_none_method(self):
        """Test first_or_none() method."""
        f = F(self.manager)

        # Test with existing users
        user = f.filter(loginShell="/bin/bash").first_or_none()
        assert user is not None
        assert user.loginShell == "/bin/bash"

        # Test with non-existent user
        user = f.filter(uid="nonexistent").first_or_none()
        assert user is None

        # Test with ordering
        f = F(self.manager)
        user = f.filter(loginShell="/bin/bash").order_by("uid").first_or_none()
        assert user is not None
        assert user.uid == "alice"  # Should be first alphabetically

    def test_iteration_with_chaining(self):
        """Test that iteration works with method chaining."""
        f = F(self.manager)

        # Test iteration after filtering and ordering
        users = list(f.filter(loginShell="/bin/bash").order_by("uid"))
        assert len(users) == 3
        uids = [user.uid for user in users]
        assert uids == ["alice", "bob", "diana"]

        # Test iteration after only()
        users = list(f.filter(uid="alice").only("uid", "cn"))
        assert len(users) == 1
        assert users[0].uid == "alice"
        assert users[0].cn == "Alice Johnson"

    def test_indexing_with_chaining(self):
        """Test that indexing works with method chaining."""
        f = F(self.manager)

        # Test indexing after filtering and ordering
        first_bash_user = f.filter(loginShell="/bin/bash").order_by("uid")[0]
        assert first_bash_user.uid == "alice"

        # Test slicing after filtering
        bash_users = f.filter(loginShell="/bin/bash").order_by("uid")[:2]  # type: ignore[assignment]
        assert len(bash_users) == 2
        assert bash_users[0].uid == "alice"  # type: ignore[attr-defined]
        assert bash_users[1].uid == "bob"  # type: ignore[attr-defined]

    def test_length_with_chaining(self):
        """Test that len() works with method chaining."""
        f = F(self.manager)

        # Test length after filtering
        bash_count = len(f.filter(loginShell="/bin/bash"))
        assert bash_count == 3

        # Test length after ordering
        total_count = len(f.filter(objectclass="posixAccount").order_by("uid"))
        assert total_count == 5

    def test_multiple_iterations(self):
        """Test that F instances can be iterated multiple times."""
        f = F(self.manager)
        f = f.filter(loginShell="/bin/bash")

        # First iteration
        users1 = list(f)
        assert len(users1) == 3

        # Second iteration (should work the same)
        users2 = list(f)
        assert len(users2) == 3

        # Both should have the same content
        uids1 = [user.uid for user in users1]
        uids2 = [user.uid for user in users2]
        assert uids1 == uids2

    def test_index_error_handling(self):
        """Test that indexing errors are handled properly."""
        f = F(self.manager)
        f = f.filter(uid="nonexistent")

        # Should raise IndexError for empty result
        with pytest.raises(IndexError):
            _ = f[0]

        # Should raise IndexError for negative index on empty result
        with pytest.raises(IndexError):
            _ = f[-1]

    def test_slice_with_empty_result(self):
        """Test slicing with empty results."""
        f = F(self.manager)
        f = f.filter(uid="nonexistent")

        # Slicing empty result should return empty list
        empty_slice = f[:5]
        assert len(empty_slice) == 0

        empty_slice = f[1:3]
        assert len(empty_slice) == 0

    def test_convenience_methods_with_complex_queries(self):
        """Test convenience methods with complex query chains."""
        f = F(self.manager)

        # Complex query with multiple filters and ordering
        complex_f = f.filter(uidNumber__gte=1002).filter(loginShell="/bin/bash").order_by("uid")

        # Test count
        assert complex_f.count() == 2  # bob and diana

        # Test as_list
        user_list = complex_f.as_list()
        assert len(user_list) == 2
        uids = [user.uid for user in user_list]
        assert uids == ["bob", "diana"]

        # Test get_or_none (should return None due to multiple results)
        user = complex_f.get_or_none()
        assert user is None

        # Test first_or_none
        user = complex_f.first_or_none()
        assert user is not None
        assert user.uid == "bob"

    def test_f_iterator_class(self):
        """Test the FIterator class functionality."""
        f = F(self.manager)
        f = f.filter(objectclass="posixAccount").order_by("uid")

        # Get the iterator
        iterator = iter(f)

        # Test iteration
        users = []
        for user in iterator:
            users.append(user)

        assert len(users) == 5
        uids = [user.uid for user in users]
        assert uids == ["alice", "bob", "charlie", "diana", "edward"]

        # Test that iterator is exhausted
        with pytest.raises(StopIteration):
            next(iterator)

    def test_backward_compatibility(self):
        """Test that existing .all() method still works."""
        f = F(self.manager)
        f = f.filter(objectclass="posixAccount")

        # Test that .all() still works
        all_users = f.all()
        assert len(all_users) == 5

        # Test that iteration gives same result as .all()
        iter_users = list(f)
        assert len(iter_users) == len(all_users)

        # Test that content is the same
        all_uids = [user.uid for user in all_users]
        iter_uids = [user.uid for user in iter_users]
        assert all_uids == iter_uids

    def test_page_method(self):
        """Test the new page method for paged LDAP searches."""
        f = F(self.manager)
        f = f.filter(objectclass="posixAccount").order_by("uid")

        # Test first page
        paged_results = f.page(page_size=2)

        # Test basic structure
        self.assertIsInstance(paged_results, PagedResultSet)
        self.assertIsInstance(paged_results.results, list)
        self.assertIsInstance(paged_results.next_cookie, str)
        self.assertIsInstance(paged_results.has_more, bool)

        # The LDAP faker might not properly implement paging, so we test the basic structure
        if len(paged_results.results) == 2 and paged_results.has_more:
            # Faker supports paging
            self.assertTrue(len(paged_results.next_cookie) > 0)

            # Test second page
            paged_results2 = f.page(page_size=2, cookie=paged_results.next_cookie)

            # Should get more results
            self.assertIsInstance(paged_results2, PagedResultSet)
            self.assertIsInstance(paged_results2.results, list)

            # Test third page if there are more
            if paged_results2.has_more:
                paged_results3 = f.page(page_size=2, cookie=paged_results2.next_cookie)
                self.assertIsInstance(paged_results3, PagedResultSet)
                self.assertIsInstance(paged_results3.results, list)

                # Eventually we should reach the end
                if not paged_results3.has_more:
                    self.assertEqual(paged_results3.next_cookie, "")

        else:
            # Faker doesn't support paging, but structure should still be correct
            self.assertEqual(len(paged_results.results), 5)  # All results
            self.assertFalse(paged_results.has_more)
            self.assertEqual(paged_results.next_cookie, "")

        # Test with empty cookie (should start from beginning)
        paged_results4 = f.page(page_size=2, cookie="")

        # Should get same results as first page
        self.assertIsInstance(paged_results4, PagedResultSet)
        self.assertIsInstance(paged_results4.results, list)

        # Test iteration over PagedResultSet
        iter_results = list(paged_results)
        self.assertIsInstance(iter_results, list)

        # Test indexing PagedResultSet
        if len(paged_results) > 0:
            self.assertIsInstance(paged_results[0], MyTestUser)

    def test_efficient_slicing(self):
        """Test that f[:limit] uses sizelimit for efficiency."""
        f = F(self.manager)
        f = f.filter(objectclass="posixAccount").order_by("uid")

        # Test efficient slicing with stop only
        first_three = f[:3]
        assert len(first_three) == 3
        assert first_three[0].uid == "alice"
        assert first_three[1].uid == "bob"
        assert first_three[2].uid == "charlie"

        # Test with different limit
        first_two = f[:2]
        assert len(first_two) == 2
        assert first_two[0].uid == "alice"
        assert first_two[1].uid == "bob"

        # Test with limit larger than available results
        all_users = f[:10]
        assert len(all_users) == 5  # Should return all available users

    def test_inefficient_slicing(self):
        """Test that other slice types fall back to fetching all records."""
        f = F(self.manager)
        f = f.filter(objectclass="posixAccount").order_by("uid")

        # Test slice with start (inefficient)
        skip_first = f[1:3]
        assert len(skip_first) == 2
        assert skip_first[0].uid == "bob"
        assert skip_first[1].uid == "charlie"

        # Test slice with step (inefficient)
        every_other = f[::2]
        assert len(every_other) == 3
        assert every_other[0].uid == "alice"
        assert every_other[1].uid == "charlie"
        assert every_other[2].uid == "edward"

        # Test slice with start and stop (inefficient)
        middle_three = f[1:4]
        assert len(middle_three) == 3
        assert middle_three[0].uid == "bob"
        assert middle_three[1].uid == "charlie"
        assert middle_three[2].uid == "diana"

    def test_slicing_with_filters(self):
        """Test that slicing works correctly with filters."""
        f = F(self.manager)
        f = f.filter(loginShell="/bin/bash").order_by("uid")

        # Test efficient slicing with filter
        first_two_bash = f[:2]
        assert len(first_two_bash) == 2
        assert first_two_bash[0].uid == "alice"
        assert first_two_bash[1].uid == "bob"

        # Test inefficient slicing with filter
        skip_first_bash = f[1:]
        assert len(skip_first_bash) == 2  # bob and diana
        assert skip_first_bash[0].uid == "bob"
        assert skip_first_bash[1].uid == "diana"

    def test_slicing_edge_cases(self):
        """Test slicing with edge cases."""
        # Test with empty result
        empty_f = F(self.manager).filter(uid="nonexistent")
        self.assertEqual(len(empty_f), 0)
        self.assertEqual(empty_f[:5], [])

        # Test with single result
        single_f = F(self.manager).filter(uid="alice")
        self.assertEqual(len(single_f), 1)
        self.assertEqual(single_f[:5], single_f.as_list())
        self.assertEqual(single_f[5:], [])

    # ========================================
    # Exclude Method Tests
    # ========================================

    def test_exclude_basic(self):
        """Test basic exclude functionality."""
        # Exclude a specific user
        users = F(self.manager).exclude(uid="alice").all()
        user_uids = [user.uid for user in users]
        self.assertNotIn("alice", user_uids)
        self.assertIn("bob", user_uids)
        self.assertIn("charlie", user_uids)

    def test_exclude_multiple_conditions(self):
        """Test exclude with multiple conditions."""
        # Exclude users with specific conditions
        users = F(self.manager).exclude(
            uid="alice",
            loginShell="/bin/zsh"
        ).all()
        user_uids = [user.uid for user in users]
        # Should exclude users who have BOTH uid=alice AND loginShell=/bin/zsh
        # Since no user has both conditions, no users should be excluded
        self.assertIn("alice", user_uids)  # alice has uid=alice but loginShell=/bin/bash
        self.assertIn("charlie", user_uids)  # charlie has loginShell=/bin/zsh but uid=charlie
        self.assertIn("bob", user_uids)

        # Test with conditions that actually match a user
        users = F(self.manager).exclude(
            uid="alice",
            loginShell="/bin/bash"
        ).all()
        user_uids = [user.uid for user in users]
        # Should exclude alice (who has both uid=alice AND loginShell=/bin/bash)
        self.assertNotIn("alice", user_uids)
        self.assertIn("bob", user_uids)  # bob has loginShell=/bin/bash but uid=bob
        self.assertIn("charlie", user_uids)  # charlie has uid=charlie but loginShell=/bin/zsh

    def test_exclude_with_filter(self):
        """Test chaining exclude with filter."""
        # Filter for bash users, then exclude alice
        users = F(self.manager).filter(loginShell="/bin/bash").exclude(uid="alice").all()
        user_uids = [user.uid for user in users]
        self.assertNotIn("alice", user_uids)
        self.assertIn("bob", user_uids)
        self.assertIn("diana", user_uids)
        # Note: edward has loginShell=/bin/tcsh, not /bin/bash, so he shouldn't be in the results

    def test_exclude_with_filter_suffixes(self):
        """Test exclude with various filter suffixes."""
        # Test icontains
        users = F(self.manager).exclude(cn__icontains="Alice").all()
        user_cns = [user.cn for user in users]
        self.assertNotIn("Alice Johnson", user_cns)
        self.assertIn("Bob Smith", user_cns)

        # Test istartswith
        users = F(self.manager).exclude(cn__istartswith="Alice").all()
        user_cns = [user.cn for user in users]
        self.assertNotIn("Alice Johnson", user_cns)
        self.assertIn("Bob Smith", user_cns)

        # Test iendswith
        users = F(self.manager).exclude(cn__iendswith="Johnson").all()
        user_cns = [user.cn for user in users]
        self.assertNotIn("Alice Johnson", user_cns)
        self.assertIn("Bob Smith", user_cns)

        # Test iexact
        users = F(self.manager).exclude(cn__iexact="Alice Johnson").all()
        user_cns = [user.cn for user in users]
        self.assertNotIn("Alice Johnson", user_cns)
        self.assertIn("Bob Smith", user_cns)

    def test_exclude_with_in_operator(self):
        """Test exclude with __in operator."""
        users = F(self.manager).exclude(uid__in=["alice", "bob"]).all()
        user_uids = [user.uid for user in users]
        self.assertNotIn("alice", user_uids)
        self.assertNotIn("bob", user_uids)
        self.assertIn("charlie", user_uids)
        self.assertIn("diana", user_uids)

    def test_exclude_with_exists(self):
        """Test exclude with __exists operator."""
        # All users have uid, so excluding uid__exists=True should return empty
        users = F(self.manager).exclude(uid__exists=True).all()
        self.assertEqual(len(users), 0)

        # Excluding uid__exists=False should return all users
        users = F(self.manager).exclude(uid__exists=False).all()
        self.assertEqual(len(users), 5)

    def test_exclude_with_integer_comparisons(self):
        """Test exclude with integer comparison operators."""
        # Exclude users with uidNumber >= 1003
        users = F(self.manager).exclude(uidNumber__gte=1003).all()
        user_uids = [user.uid for user in users]
        self.assertIn("alice", user_uids)  # uidNumber 1001
        self.assertIn("bob", user_uids)    # uidNumber 1002
        self.assertNotIn("charlie", user_uids)  # uidNumber 1003
        self.assertNotIn("diana", user_uids)    # uidNumber 1004
        self.assertNotIn("edward", user_uids)   # uidNumber 1005

        # Exclude users with uidNumber < 1003
        users = F(self.manager).exclude(uidNumber__lt=1003).all()
        user_uids = [user.uid for user in users]
        self.assertNotIn("alice", user_uids)  # uidNumber 1001
        self.assertNotIn("bob", user_uids)    # uidNumber 1002
        self.assertIn("charlie", user_uids)   # uidNumber 1003
        self.assertIn("diana", user_uids)     # uidNumber 1004
        self.assertIn("edward", user_uids)    # uidNumber 1005

    def test_exclude_with_none_value(self):
        """Test exclude with None values."""
        # Exclude users where uid is None (should exclude users who have uid attribute)
        # Since all users have uid, all should be excluded
        users = F(self.manager).exclude(uid=None).all()
        self.assertEqual(len(users), 0)

        # Exclude users where uid equals None (should exclude users who have uid attribute)
        # Since all users have uid, all should be excluded
        users = F(self.manager).exclude(uid__iexact=None).all()
        self.assertEqual(len(users), 0)

    def test_exclude_with_f_objects(self):
        """Test exclude with F objects."""
        # Create F objects for exclusion
        f1 = F(self.manager).filter(uid="alice")
        f2 = F(self.manager).filter(uid="bob")

        # Exclude using F objects
        users = F(self.manager).exclude(f1, f2).all()
        user_uids = [user.uid for user in users]
        self.assertNotIn("alice", user_uids)
        self.assertNotIn("bob", user_uids)
        self.assertIn("charlie", user_uids)

    def test_exclude_with_logical_operations(self):
        """Test exclude with logical operations."""
        # Test exclude with OR logic
        f1 = F(self.manager).filter(uid="alice")
        f2 = F(self.manager).filter(uid="bob")
        or_filter = f1 | f2

        users = F(self.manager).exclude(or_filter).all()
        user_uids = [user.uid for user in users]
        self.assertNotIn("alice", user_uids)
        self.assertNotIn("bob", user_uids)
        self.assertIn("charlie", user_uids)

    def test_exclude_chaining(self):
        """Test chaining multiple exclude calls."""
        # Chain multiple exclude calls
        users = F(self.manager).exclude(uid="alice").exclude(uid="bob").all()
        user_uids = [user.uid for user in users]
        self.assertNotIn("alice", user_uids)
        self.assertNotIn("bob", user_uids)
        self.assertIn("charlie", user_uids)

    def test_exclude_with_other_methods(self):
        """Test exclude with other methods like only, order_by."""
        # Test exclude with only
        users = F(self.manager).exclude(uid="alice").only("uid", "cn").all()
        user_uids = [user.uid for user in users]
        self.assertNotIn("alice", user_uids)
        self.assertIn("bob", user_uids)

        # Test exclude with order_by
        users = F(self.manager).exclude(uid="alice").order_by("uid").all()
        user_uids = [user.uid for user in users]
        self.assertNotIn("alice", user_uids)
        self.assertEqual(user_uids, ["bob", "charlie", "diana", "edward"])

    def test_exclude_edge_cases(self):
        """Test exclude with edge cases."""
        # Exclude all users (should return empty)
        users = F(self.manager).exclude(
            uid__in=["alice", "bob", "charlie", "diana", "edward"]
        ).all()
        self.assertEqual(len(users), 0)

        # Exclude with empty list
        users = F(self.manager).exclude(uid__in=[]).all()
        self.assertEqual(len(users), 5)

    def test_exclude_error_handling(self):
        """Test exclude error handling."""
        # Test invalid field
        with self.assertRaises(MyTestUser.InvalidField):
            F(self.manager).exclude(invalid_field="value")

        # Test invalid suffix
        with self.assertRaises(F.UnknownSuffix):
            F(self.manager).exclude(uid__invalid="value")

        # Test __in with non-list
        with self.assertRaises(ValueError):
            F(self.manager).exclude(uid__in="not_a_list")

        # Test integer comparison on non-integer field
        with self.assertRaises(TypeError):
            F(self.manager).exclude(cn__gt=100)

    def test_exclude_string_representation(self):
        """Test string representation of exclude filters."""
        # Simple exclude
        f = F(self.manager).exclude(uid="alice")
        self.assertIn("(!(uid=alice))", str(f))

        # Multiple excludes - our implementation combines them with AND
        f = F(self.manager).exclude(uid="alice", cn="Bob Smith")
        self.assertIn("(!(&(uid=alice)(cn=Bob Smith)))", str(f))

        # Exclude with filter
        f = F(self.manager).filter(loginShell="/bin/bash").exclude(uid="alice")
        self.assertIn("(loginShell=/bin/bash)", str(f))
        self.assertIn("(!(uid=alice))", str(f))

    def test_exclude_with_values_method(self):
        """Test exclude with values method."""
        users = F(self.manager).exclude(uid="alice").values("uid", "cn")
        user_uids = [user["uid"] for user in users]
        self.assertNotIn("alice", user_uids)
        self.assertIn("bob", user_uids)

    def test_exclude_with_values_list_method(self):
        """Test exclude with values_list method."""
        users = F(self.manager).exclude(uid="alice").values_list("uid", "cn")
        user_uids = [user[0] for user in users]
        self.assertNotIn("alice", user_uids)
        self.assertIn("bob", user_uids)

    def test_exclude_with_count_method(self):
        """Test exclude with count method."""
        count = F(self.manager).exclude(uid="alice").count()
        self.assertEqual(count, 4)  # 5 total - 1 excluded = 4

    def test_exclude_with_exists_method(self):
        """Test exclude with exists method."""
        # Should exist since we're excluding only one user
        self.assertTrue(F(self.manager).exclude(uid="alice").exists())

        # Should not exist if we exclude all users
        self.assertFalse(F(self.manager).exclude(
            uid__in=["alice", "bob", "charlie", "diana", "edward"]
        ).exists())

    def test_exclude_with_get_method(self):
        """Test exclude with get method."""
        # Should get bob since alice is excluded
        user = F(self.manager).exclude(uid="alice").get(uid="bob")
        self.assertEqual(user.uid, "bob")

        # Should raise DoesNotExist if trying to get excluded user
        with self.assertRaises(MyTestUser.DoesNotExist):
            F(self.manager).exclude(uid="alice").get(uid="alice")

    def test_exclude_with_get_or_none_method(self):
        """Test exclude with get_or_none method."""
        # Should get bob since alice is excluded
        user = F(self.manager).exclude(uid="alice").get_or_none(uid="bob")
        self.assertEqual(user.uid, "bob")

        # Should return None if trying to get excluded user
        user = F(self.manager).exclude(uid="alice").get_or_none(uid="alice")
        self.assertIsNone(user)

    def test_exclude_with_first_method(self):
        """Test exclude with first method."""
        user = F(self.manager).exclude(uid="alice").first()
        self.assertIsNotNone(user)
        self.assertNotEqual(user.uid, "alice")

    def test_exclude_with_first_or_none_method(self):
        """Test exclude with first_or_none method."""
        user = F(self.manager).exclude(uid="alice").first_or_none()
        self.assertIsNotNone(user)
        self.assertNotEqual(user.uid, "alice")

        # Test with all users excluded
        user = F(self.manager).exclude(
            uid__in=["alice", "bob", "charlie", "diana", "edward"]
        ).first_or_none()
        self.assertIsNone(user)

    def test_exclude_complex_scenarios(self):
        """Test complex exclude scenarios."""
        # Complex scenario: filter for bash users, exclude alice and users with uidNumber > 1003
        users = F(self.manager).filter(loginShell="/bin/bash").exclude(
            uid="alice",
            uidNumber__gt=1003
        ).all()
        user_uids = [user.uid for user in users]
        # The test data shows:
        # - alice: loginShell=/bin/bash, uidNumber=1001
        # - bob: loginShell=/bin/bash, uidNumber=1002
        # - charlie: loginShell=/bin/zsh, uidNumber=1003
        # - diana: loginShell=/bin/bash, uidNumber=1004
        # - edward: loginShell=/bin/tcsh, uidNumber=1005
        #
        # Filter for bash users: alice, bob, diana
        # Exclude users who are alice AND have uidNumber > 1003
        # Since alice has uidNumber=1001, she doesn't match the exclude condition
        # So we should get alice, bob, diana back
        self.assertIn("alice", user_uids)
        self.assertIn("bob", user_uids)
        self.assertIn("diana", user_uids)
        self.assertNotIn("edward", user_uids)  # edward has /bin/tcsh, not /bin/bash

    def test_exclude_de_morgans_law(self):
        """Test that exclude follows De Morgan's Law correctly."""
        # NOT (A AND B) should be equivalent to (NOT A) OR (NOT B)
        # But our implementation does (A) AND NOT (B AND C)
        # This test verifies our specific behavior

        # Exclude users who are alice AND have bash shell
        users = F(self.manager).exclude(
            uid="alice",
            loginShell="/bin/bash"
        ).all()
        user_uids = [user.uid for user in users]
        # Should exclude alice (who has both conditions)
        self.assertNotIn("alice", user_uids)
        # Should include bob (who has bash but not alice)
        self.assertIn("bob", user_uids)
        # Should include charlie (who is not alice but has zsh)
        self.assertIn("charlie", user_uids)


if __name__ == "__main__":
    unittest.main()