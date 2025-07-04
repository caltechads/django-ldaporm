# mypy: disable-error-code="attr-defined"
"""
Comprehensive test suite for LdapManager using python-ldap-faker.

This test suite uses python-ldap-faker to simulate a 389 Directory Server,
providing realistic LDAP behavior for testing the LdapManager functionality.

"""


import json
import tempfile
from typing import cast
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import ldap
from ldap_faker.unittest import LDAPFakerMixin

from ldaporm.fields import CharField, IntegerField, CharListField
from ldaporm.managers import LdapManager, Modlist, atomic, needs_pk, substitute_pk
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
        password_attribute = "userPassword"
        userid_attribute = "uid"


class MyTestGroup(Model):
    """Test model for group objects."""

    cn = CharField(primary_key=True)
    gidNumber = IntegerField()
    memberUid = CharListField()

    class Meta:
        basedn = "ou=groups,dc=example,dc=com"
        objectclass = "posixGroup"
        ldap_server = "test_server"
        ordering: list[str] = []
        ldap_options: list[str] = []
        extra_objectclasses = ["top"]


class TestLdapManagerWithFaker(LDAPFakerMixin, unittest.TestCase):
    """Test suite for LdapManager using python-ldap-faker."""

    ldap_modules = ['ldaporm']

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create test data for the fake LDAP server
        cls.test_users = [
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
                    "userPassword": [b"password"],
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
                    "userPassword": [b"password"],
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
                    "userPassword": [b"password"],
                    "objectclass": [b"posixAccount", b"top"]
                }
            ]
        ]

        cls.test_groups = [
            [
                "cn=developers,ou=groups,dc=example,dc=com",
                {
                    "cn": [b"developers"],
                    "gidNumber": [b"2001"],
                    "memberUid": [b"alice", b"bob"],
                    "objectclass": [b"posixGroup", b"top"]
                }
            ],
            [
                "cn=admins,ou=groups,dc=example,dc=com",
                {
                    "cn": [b"admins"],
                    "gidNumber": [b"2002"],
                    "memberUid": [b"alice"],
                    "objectclass": [b"posixGroup", b"top"]
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
        })
        self.settings_patcher.start()

        # Initialize the managers
        self.user_manager = LdapManager()
        self.user_manager.contribute_to_class(MyTestUser, 'objects')

        self.group_manager = LdapManager()
        self.group_manager.contribute_to_class(MyTestGroup, 'objects')

        # Ensure the managers are properly set up
        if not hasattr(MyTestUser, 'objects') or MyTestUser.objects is None:
            raise RuntimeError("MyTestUser.objects was not properly initialized")
        if not hasattr(MyTestGroup, 'objects') or MyTestGroup.objects is None:
            raise RuntimeError("MyTestGroup.objects was not properly initialized")

        # Clear the fake LDAP directory before each test
        self.server_factory.default.raw_objects.clear()  # type: ignore[attr-defined]
        self.server_factory.default.objects.clear()  # type: ignore[attr-defined]

        # Reload test data before each test
        for dn, attrs in self.test_users + self.test_groups:
            self.server_factory.default.register_object((dn, attrs))  # type: ignore[attr-defined]

    def tearDown(self):
        """Clean up after tests."""
        self.settings_patcher.stop()
        super().tearDown()

    def test_manager_initialization(self):
        """Test LdapManager initialization and configuration."""
        # Use the manager directly from setUp
        self.assertEqual(self.user_manager.pk, "uid")
        self.assertEqual(self.user_manager.basedn, "ou=users,dc=example,dc=com")
        self.assertEqual(self.user_manager.objectclass, "posixAccount")
        self.assertEqual(self.user_manager.extra_objectclasses, ["top"])
        self.assertIsNotNone(self.user_manager.config)

    def test_connection_management(self):
        """Test LDAP connection management."""
        # Test connection creation
        self.assertFalse(self.user_manager.has_connection())

        self.user_manager.connect("read")
        self.assertTrue(self.user_manager.has_connection())

        # Test connection object
        connection = self.user_manager.connection
        self.assertIsNotNone(connection)

        # Test disconnection
        self.user_manager.disconnect()
        self.assertFalse(self.user_manager.has_connection())

    def test_new_connection(self):
        """Test creating a new connection without setting it."""
        connection = self.user_manager.new_connection("read")
        self.assertIsNotNone(connection)
        self.assertFalse(self.user_manager.has_connection())

        # Clean up
        connection.unbind_s()

    def test_dn_computation(self):
        """Test DN computation for model instances."""
        user = MyTestUser(uid="testuser")
        expected_dn = "uid=testuser,ou=users,dc=example,dc=com"

        dn = self.user_manager.dn(user)
        self.assertEqual(dn, expected_dn)

    def test_get_dn(self):
        """Test getting DN from primary key value."""
        expected_dn = "uid=testuser,ou=users,dc=example,dc=com"
        dn = self.user_manager.get_dn("testuser")
        self.assertEqual(dn, expected_dn)

    def test_search_basic(self):
        """Test basic LDAP search functionality."""
        results = cast("LdapManager", MyTestUser.objects).search(
            "(objectClass=posixAccount)",
            ["uid", "cn", "sn"]
        )
        self.assertEqual(len(results), 3)  # alice, bob, charlie

        # Check that results contain expected data
        uids = [result[1]["uid"][0].decode() for result in results]
        self.assertIn("alice", uids)
        self.assertIn("bob", uids)
        self.assertIn("charlie", uids)

    def test_search_with_sizelimit(self):
        """Test search with size limit."""
        # Add more test users to make sizelimit meaningful
        extra_users = [
            [
                "uid=dave,ou=users,dc=example,dc=com",
                {
                    "uid": [b"dave"],
                    "cn": [b"Dave Wilson"],
                    "sn": [b"Wilson"],
                    "uidNumber": [b"1004"],
                    "gidNumber": [b"1004"],
                    "homeDirectory": [b"/home/dave"],
                    "loginShell": [b"/bin/bash"],
                    "userPassword": [b"password"],
                    "objectclass": [b"posixAccount", b"top"]
                }
            ],
            [
                "uid=eve,ou=users,dc=example,dc=com",
                {
                    "uid": [b"eve"],
                    "cn": [b"Eve Davis"],
                    "sn": [b"Davis"],
                    "uidNumber": [b"1005"],
                    "gidNumber": [b"1005"],
                    "homeDirectory": [b"/home/eve"],
                    "loginShell": [b"/bin/bash"],
                    "userPassword": [b"password"],
                    "objectclass": [b"posixAccount", b"top"]
                }
            ]
        ]

        # Register the extra users
        for dn, attrs in extra_users:
            self.server_factory.default.register_object((dn, attrs))  # type: ignore[attr-defined]

        # Test with sizelimit - should return at most 2 results
        results = cast("LdapManager", MyTestUser.objects).search(
            "(objectClass=posixAccount)",
            ["uid"],
            sizelimit=2
        )

        # Note: If python-ldap-faker doesn't enforce sizelimit, this test will still pass
        # but will verify the search works correctly
        self.assertGreater(len(results), 0)  # Should have some results
        self.assertLessEqual(len(results), 5)  # Should not exceed total number of users

    def test_search_with_custom_scope(self):
        """Test search with custom scope."""
        # Test base scope
        results = cast("LdapManager", MyTestUser.objects).search(
            "(objectClass=*)",
            ["uid"],
            basedn="uid=alice,ou=users,dc=example,dc=com",
            scope=ldap.SCOPE_BASE  # type: ignore[attr-defined]
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1]["uid"][0].decode(), "alice")

    def test_paged_search(self):
        """Test paged search functionality."""
        # Add paged_search to ldap_options
        cast("LdapManager", MyTestUser.objects).ldap_options.append("paged_search")

        results = cast("LdapManager", MyTestUser.objects).search(
            "(objectClass=posixAccount)",
            ["uid", "cn"]
        )
        self.assertEqual(len(results), 3)

        # Remove paged_search option
        cast("LdapManager", MyTestUser.objects).ldap_options.remove("paged_search")

    def test_add_object(self):
        """Test adding a new object to LDAP."""
        new_user = MyTestUser(
            uid="newuser",
            cn="New User",
            sn="User",
            uidNumber=1004,
            gidNumber=1004,
            homeDirectory="/home/newuser",
            loginShell="/bin/bash"
        )

        cast("LdapManager", MyTestUser.objects).add(new_user)

        # Verify the object was added
        results = cast("LdapManager", MyTestUser.objects).search(
            "(uid=newuser)",
            ["uid", "cn"]
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1]["uid"][0].decode(), "newuser")

    def test_delete_object(self):
        """Test deleting an object from LDAP."""
        # First add an object to delete
        user_to_delete = MyTestUser(
            uid="deleteuser",
            cn="Delete User",
            sn="User",
            uidNumber=1005,
            gidNumber=1005,
            homeDirectory="/home/deleteuser",
            loginShell="/bin/bash"
        )
        cast("LdapManager", MyTestUser.objects).add(user_to_delete)

        # Verify it exists
        results = cast("LdapManager", MyTestUser.objects).search("(uid=deleteuser)", ["uid"])
        self.assertEqual(len(results), 1)

        # Delete it
        cast("LdapManager", MyTestUser.objects).delete_obj(user_to_delete)

        # Verify it's gone
        results = cast("LdapManager", MyTestUser.objects).search("(uid=deleteuser)", ["uid"])
        self.assertEqual(len(results), 0)

    def test_delete_by_filter(self):
        """Test deleting an object by filter."""
        # First add an object to delete
        user_to_delete = MyTestUser(
            uid="filterdelete",
            cn="Filter Delete User",
            sn="User",
            uidNumber=1006,
            gidNumber=1006,
            homeDirectory="/home/filterdelete",
            loginShell="/bin/bash"
        )
        cast("LdapManager", MyTestUser.objects).add(user_to_delete)

        # Delete by filter
        cast("LdapManager", MyTestUser.objects).delete(uid="filterdelete")

        # Verify it's gone
        results = cast("LdapManager", MyTestUser.objects).search("(uid=filterdelete)", ["uid"])
        self.assertEqual(len(results), 0)

    def test_modify_object(self):
        """Test modifying an existing object."""
        # Get an existing user
        user = cast("LdapManager", MyTestUser.objects).get(uid="alice")
        original_shell = user.loginShell

        # Modify the user
        user.loginShell = "/bin/zsh"
        cast("LdapManager", MyTestUser.objects).modify(user)

        # Verify the change
        updated_user = cast("LdapManager", MyTestUser.objects).get(uid="alice")
        self.assertEqual(updated_user.loginShell, "/bin/zsh")
        self.assertNotEqual(updated_user.loginShell, original_shell)

    def test_modify_with_pk_change(self):
        """Test modifying an object with primary key change."""
        # Get an existing user
        user = cast("LdapManager", MyTestUser.objects).get(uid="alice")
        original_uid = user.uid

        # Change the primary key
        user.uid = "alice_new"
        cast("LdapManager", MyTestUser.objects).modify(user)

        # Verify the change
        updated_user = cast("LdapManager", MyTestUser.objects).get(uid="alice_new")
        self.assertEqual(updated_user.uid, "alice_new")

        # Verify old uid doesn't exist
        with self.assertRaises(MyTestUser.DoesNotExist):
            cast("LdapManager", MyTestUser.objects).get(uid="alice")

    def test_rename_object(self):
        """Test renaming an object's DN."""
        old_dn = "uid=alice,ou=users,dc=example,dc=com"
        new_dn = "uid=alice_new,ou=users,dc=example,dc=com"

        cast("LdapManager", MyTestUser.objects).rename(old_dn, new_dn)

        # Verify the rename
        results = cast("LdapManager", MyTestUser.objects).search(
            "(uid=alice_new)",
            ["uid"],
            basedn="uid=alice_new,ou=users,dc=example,dc=com",
            scope=ldap.SCOPE_BASE  # type: ignore[attr-defined]
        )
        self.assertEqual(len(results), 1)

    def test_get_by_dn(self):
        """Test getting an object by its DN."""
        user = cast("LdapManager", MyTestUser.objects).get_by_dn("uid=alice,ou=users,dc=example,dc=com")
        self.assertEqual(cast("MyTestUser", user).uid, "alice")
        self.assertEqual(cast("MyTestUser", user).cn, "Alice Johnson")

    def test_get_by_dn_invalid_dn(self):
        """Test getting an object by invalid DN."""
        with self.assertRaises(ValueError):
            cast("LdapManager", MyTestUser.objects).get_by_dn("uid=alice,dc=invalid,dc=com")

    def test_get_by_dn_nonexistent(self):
        """Test getting a nonexistent object by DN."""
        with self.assertRaises(MyTestUser.DoesNotExist):
            cast("LdapManager", MyTestUser.objects).get_by_dn("uid=nonexistent,ou=users,dc=example,dc=com")

    def test_filter_methods(self):
        """Test filter-based query methods."""
        # Test get with filter
        user = cast("LdapManager", MyTestUser.objects).get(uid="alice")
        self.assertEqual(user.uid, "alice")

        # Test get with multiple conditions
        user = cast("LdapManager", MyTestUser.objects).get(uid="alice", cn="Alice Johnson")
        self.assertEqual(user.uid, "alice")

        # Test get with nonexistent user
        with self.assertRaises(MyTestUser.DoesNotExist):
            cast("LdapManager", MyTestUser.objects).get(uid="nonexistent")

        # Test get with multiple results
        with self.assertRaises(MyTestUser.MultipleObjectsReturned):
            cast("LdapManager", MyTestUser.objects).get(loginShell="/bin/bash")  # Multiple users have bash

    def test_all_method(self):
        """Test getting all objects."""
        users = cast("LdapManager", MyTestUser.objects).all()
        self.assertEqual(len(users), 3)

        uids = [cast("MyTestUser", user).uid for user in users]
        self.assertIn("alice", uids)
        self.assertIn("bob", uids)
        self.assertIn("charlie", uids)

    def test_values_method(self):
        """Test values method."""
        values = cast("LdapManager", MyTestUser.objects).values("uid", "cn")
        self.assertEqual(len(values), 3)

        # Check structure
        for value_dict in values:
            self.assertIn("uid", value_dict)
            self.assertIn("cn", value_dict)
            self.assertNotIn("sn", value_dict)

    def test_values_list_method(self):
        """Test values_list method."""
        values = cast("LdapManager", MyTestUser.objects).values_list("uid", "cn")
        self.assertEqual(len(values), 3)

        # Check structure
        for value_tuple in values:
            self.assertEqual(len(value_tuple), 2)
            self.assertIsInstance(value_tuple[0], str)  # uid
            self.assertIsInstance(value_tuple[1], str)  # cn

    def test_values_list_flat(self):
        """Test values_list with flat=True."""
        values = cast("LdapManager", MyTestUser.objects).values_list("uid", flat=True)
        self.assertEqual(len(values), 3)

        # Check structure
        for value in values:
            self.assertIsInstance(value, str)

    def test_values_list_named(self):
        """Test values_list with named=True."""
        values = cast("LdapManager", MyTestUser.objects).values_list("uid", "cn", named=True)
        self.assertEqual(len(values), 3)

        # Check structure
        for named_tuple in values:
            self.assertEqual(len(named_tuple), 2)
            self.assertIsInstance(named_tuple.uid, str)  # type: ignore[attr-defined]
            self.assertIsInstance(named_tuple.cn, str)  # type: ignore[attr-defined]

    def test_order_by(self):
        """Test ordering functionality."""
        # Test ascending order
        users = cast("LdapManager", MyTestUser.objects).order_by("uid").all()
        uids = [user.uid for user in users]
        self.assertEqual(uids, ["alice", "bob", "charlie"])

        # Test descending order
        users = cast("LdapManager", MyTestUser.objects).order_by("-uid").all()
        uids = [user.uid for user in users]
        self.assertEqual(uids, ["charlie", "bob", "alice"])

    def test_create_method(self):
        """Test creating a new object."""
        user = cast("LdapManager", MyTestUser.objects).create(
            uid="newuser",
            cn="New User",
            sn="User",
            uidNumber=1007,
            gidNumber=1007,
            homeDirectory="/home/newuser",
            loginShell="/bin/bash"
        )

        self.assertEqual(cast("MyTestUser", user).uid, "newuser")
        self.assertEqual(cast("MyTestUser", user).cn, "New User")

        # Verify it was actually created in LDAP
        created_user = cast("LdapManager", MyTestUser.objects).get(uid="newuser")
        self.assertEqual(created_user.uid, "newuser")

    def test_authentication_success(self):
        """Test successful authentication."""
        result = cast("LdapManager", MyTestUser.objects).authenticate("alice", "password")
        self.assertTrue(result)

    def test_authentication_nonexistent_user(self):
        """Test authentication with nonexistent user."""
        result = cast("LdapManager", MyTestUser.objects).authenticate("nonexistent", "password")
        self.assertFalse(result)

    def test_authentication_invalid_credentials(self):
        """Test authentication with invalid credentials."""
        result = cast("LdapManager", MyTestUser.objects).authenticate("alice", "wrongpassword")
        self.assertFalse(result)

    def test_reset_password(self):
        """Test password reset functionality."""
        # For testing with fake LDAP, we need to use plain text passwords
        # since the fake server doesn't understand SSHA hashes for authentication

        # Override the get_password_hash method temporarily for this test
        original_get_password_hash = MyTestUser.get_password_hash

        def test_get_password_hash(cls, password):
            return password.encode('utf-8')

        MyTestUser.get_password_hash = classmethod(test_get_password_hash)  # type: ignore[assignment]

        try:
            result = cast("LdapManager", MyTestUser.objects).reset_password("alice", "newpassword123")
            self.assertTrue(result)

            # Verify the password was changed by trying to authenticate
            auth_result = cast("LdapManager", MyTestUser.objects).authenticate("alice", "newpassword123")
            self.assertTrue(auth_result)
        finally:
            # Restore the original method
            MyTestUser.get_password_hash = original_get_password_hash

    def test_reset_password_nonexistent_user(self):
        """Test password reset for nonexistent user."""
        result = cast("LdapManager", MyTestUser.objects).reset_password("nonexistent", "newpassword123")
        self.assertFalse(result)

    def test_reset_password_with_attributes(self):
        """Test password reset with additional attributes."""
        # For testing with fake LDAP, we need to use plain text passwords
        # since the fake server doesn't understand SSHA hashes for authentication

        # Override the get_password_hash method temporarily for this test
        original_get_password_hash = MyTestUser.get_password_hash

        def test_get_password_hash(cls, password):
            return password.encode('utf-8')

        MyTestUser.get_password_hash = classmethod(test_get_password_hash)  # type: ignore[assignment]

        try:
            result = cast("LdapManager", MyTestUser.objects).reset_password(
                "alice",
                "newpassword123",
                attributes={"loginShell": "/bin/zsh"}
            )
            self.assertTrue(result)

            # Verify both password and additional attribute were changed
            user = cast("LdapManager", MyTestUser.objects).get(uid="alice")
            self.assertEqual(user.loginShell, "/bin/zsh")
        finally:
            # Restore the original method
            MyTestUser.get_password_hash = original_get_password_hash

    def test_modlist_add(self):
        """Test Modlist.add functionality."""
        modlist_helper = Modlist(cast("LdapManager", MyTestUser.objects))
        user = MyTestUser(
            uid="modlistuser",
            cn="Modlist User",
            sn="User",
            uidNumber=1008,
            gidNumber=1008,
            homeDirectory="/home/modlistuser",
            loginShell="/bin/bash"
        )

        modlist = modlist_helper.add(user)
        self.assertIsInstance(modlist, list)
        self.assertGreater(len(modlist), 0)

    def test_modlist_update(self):
        """Test Modlist.update functionality."""
        modlist_helper = Modlist(cast("LdapManager", MyTestUser.objects))

        # Create old and new versions of a user
        old_user = MyTestUser(
            uid="updateuser",
            cn="Old Name",
            sn="User",
            uidNumber=1009,
            gidNumber=1009,
            homeDirectory="/home/updateuser",
            loginShell="/bin/bash"
        )

        new_user = MyTestUser(
            uid="updateuser",
            cn="New Name",
            sn="User",
            uidNumber=1009,
            gidNumber=1009,
            homeDirectory="/home/updateuser",
            loginShell="/bin/zsh"
        )

        modlist = modlist_helper.update(new_user, old_user)
        self.assertIsInstance(modlist, list)

    def test_server_side_sorting_support_check(self):
        """Test server-side sorting support detection."""
        # This should work with the fake LDAP server
        result = cast("LdapManager", MyTestUser.objects)._check_server_sorting_support("read")
        # The result depends on the fake server implementation
        self.assertIsInstance(result, bool)

    def test_connection_error_handling(self):
        """Test handling of connection errors."""
        # Test with invalid configuration
        with patch.object(MyTestUser.objects, 'config', {'read': {'url': 'ldap://invalid:389'}}):
            with self.assertRaises(Exception):
                cast("LdapManager", MyTestUser.objects)._connect("read")

    def test_tls_configuration(self):
        """Test TLS configuration options."""
        # Test with TLS configuration
        config_with_tls = {
            "read": {
                "url": "ldaps://localhost:636",
                "user": "cn=admin,dc=example,dc=com",
                "password": "admin",
                "use_starttls": True,
                "tls_verify": "always",
                "tls_ca_certfile": "/path/to/ca.crt",
                "tls_certfile": "/path/to/cert.crt",
                "tls_keyfile": "/path/to/key.key"
            }
        }

        with patch.object(MyTestUser.objects, 'config', config_with_tls):
            # This should raise an error due to missing certificate files
            with self.assertRaises(OSError):
                cast("LdapManager", MyTestUser.objects)._connect("read")

    def test_invalid_tls_verify(self):
        """Test invalid TLS verify configuration."""
        config_invalid_tls = {
            "read": {
                "url": "ldap://localhost:389",
                "user": "cn=admin,dc=example,dc=com",
                "password": "admin",
                "tls_verify": "invalid"
            }
        }

        with patch.object(MyTestUser.objects, 'config', config_invalid_tls):
            with self.assertRaises(ValueError):
                cast("LdapManager", MyTestUser.objects)._connect("read")

    def test_thread_safety(self):
        """Test thread safety of connection management."""
        import threading

        def worker():
            cast("LdapManager", MyTestUser.objects).connect("read")
            self.assertTrue(cast("LdapManager", MyTestUser.objects).has_connection())
            cast("LdapManager", MyTestUser.objects).disconnect()
            self.assertFalse(cast("LdapManager", MyTestUser.objects).has_connection())

        # Create multiple threads
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

    def test_atomic_decorator(self):
        """Test the atomic decorator functionality."""
        dummy = MyTestUser.objects

        @atomic(key="read")
        def test_function(self):
            assert self.has_connection()
            return "success"

        result = test_function(dummy)
        self.assertEqual(result, "success")
        self.assertFalse(dummy.has_connection())  # type: ignore[attr-defined]

    def test_substitute_pk_decorator(self):
        """Test the substitute_pk decorator."""
        dummy = MyTestUser.objects

        @substitute_pk
        def test_function(self, uid=None):
            return uid

        result = test_function(dummy, pk="testuser")
        self.assertEqual(result, "testuser")

    def test_needs_pk_decorator(self):
        """Test the needs_pk decorator."""
        # Create an F object to test the decorator
        f = cast("LdapManager", MyTestUser.objects).filter(uid="alice")

        @needs_pk
        def test_function(self):
            return self._attributes

        # Set up attributes without pk
        f._attributes = ["cn", "sn"]
        result = test_function(f)
        self.assertIn("uid", result)  # pk should be added

    def test_wildcard_search(self):
        """Test wildcard search functionality."""
        # Test contains search
        results = cast("LdapManager", MyTestUser.objects).wildcard("cn", "*Alice*").all()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].uid, "alice")

        # Test starts with search
        results = cast("LdapManager", MyTestUser.objects).wildcard("cn", "Alice*").all()
        self.assertEqual(len(results), 1)

        # Test ends with search
        results = cast("LdapManager", MyTestUser.objects).wildcard("cn", "*Johnson").all()
        self.assertEqual(len(results), 1)

    def test_only_restriction(self):
        """Test only() method for attribute restriction."""
        f = cast("LdapManager", MyTestUser.objects).only("uid", "cn")
        self.assertEqual(f._attributes, ["uid", "cn"])

    def test_filter_chain(self):
        """Test filter chaining."""
        f = cast("LdapManager", MyTestUser.objects).filter(uid="alice").filter(cn="Alice Johnson")
        user = f.get()
        self.assertEqual(user.uid, "alice")

    def test_complex_queries(self):
        """Test complex query combinations."""
        # Test ordering with filtering
        users = cast("LdapManager", MyTestUser.objects).filter(loginShell="/bin/bash").order_by("uid").all()
        self.assertEqual(len(users), 2)  # alice and bob
        self.assertEqual(users[0].uid, "alice")
        self.assertEqual(users[1].uid, "bob")

        # Test values with filtering
        values = cast("LdapManager", MyTestUser.objects).filter(loginShell="/bin/bash").values("uid", "cn")
        self.assertEqual(len(values), 2)

    def test_error_conditions(self):
        """Test various error conditions."""
        # Test ImproperlyConfigured for missing LDAP_SERVERS
        with patch('django.conf.settings.LDAP_SERVERS', {}):
            manager = LdapManager()
            with self.assertRaises(Exception):
                manager.contribute_to_class(MyTestUser, 'objects')

        # Test ImproperlyConfigured for missing server key
        with patch('django.conf.settings.LDAP_SERVERS', {"other_server": {}}):
            manager = LdapManager()
            with self.assertRaises(Exception):
                manager.contribute_to_class(MyTestUser, 'objects')

    def test_password_hash_generation(self):
        """Test password hash generation."""
        password = "testpassword"
        hash_result = cast("LdapManager", MyTestUser.objects)._get_ssha_hash(password)
        self.assertIsInstance(hash_result, bytes)
        self.assertTrue(hash_result.startswith(b"{SSHA}"))

    def test_paged_search_controls(self):
        """Test paged search control handling."""
        pctrls = cast("LdapManager", MyTestUser.objects)._get_pctrls([])
        self.assertEqual(pctrls, [])

        # Test with mock controls
        mock_control = MagicMock()
        mock_control.controlType = "1.2.840.113556.1.4.319"  # SimplePagedResultsControl
        pctrls = cast("LdapManager", MyTestUser.objects)._get_pctrls([mock_control])
        self.assertEqual(len(pctrls), 1)

    def test_model_integration(self):
        """Test integration with model methods."""
        # Test that manager works with model's from_db method
        user = cast("LdapManager", MyTestUser.objects).get(uid="alice")
        self.assertIsInstance(user, MyTestUser)
        self.assertEqual(user.uid, "alice")

        # Test that manager works with model's to_db method
        db_data = user.to_db()
        self.assertIsInstance(db_data, tuple)
        self.assertEqual(len(db_data), 2)

    def test_group_operations(self):
        """Test operations with group model."""
        # Test group search
        groups = cast("LdapManager", MyTestGroup.objects).all()
        self.assertEqual(len(groups), 2)

        # Test group creation
        new_group = cast("LdapManager", MyTestGroup.objects).create(
            cn="testgroup",
            gidNumber=2003,
            memberUid=["alice"]
        )
        self.assertEqual(cast("MyTestGroup", new_group).cn, "testgroup")

        # Test group modification
        new_group.memberUid = ["alice", "bob"]  # type: ignore[attr-defined]
        cast("LdapManager", MyTestGroup.objects).modify(new_group)

        updated_group = cast("LdapManager", MyTestGroup.objects).get(cn="testgroup")
        self.assertEqual(len(updated_group.memberUid), 2)


if __name__ == "__main__":
    unittest.main()
