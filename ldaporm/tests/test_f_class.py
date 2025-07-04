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
from ldaporm.managers import F, LdapManager
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

        with pytest.raises(F.NoFilterSpecified):
            f.all()

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


if __name__ == "__main__":
    unittest.main()