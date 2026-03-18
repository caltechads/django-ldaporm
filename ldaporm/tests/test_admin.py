# mypy: disable-error-code="attr-defined"
"""
Unit tests for Django Admin integration with ldaporm models.

This module validates that ldaporm models can be used with Django's admin
interface, including ModelAdmin registration, form generation, changelist
views, and queryset operations.
"""

import unittest
from unittest.mock import patch

import django
from django.conf import settings
from django.contrib import admin
from django.test import RequestFactory

from ldap_faker.unittest import LDAPFakerMixin

from ldaporm.fields import CharField, CharListField, IntegerField
from ldaporm.managers import LdapManager
from ldaporm.models import Model

# Configure Django settings before any model is defined
if not settings.configured:
    settings.configure(
        INSTALLED_APPS=[
            "django.contrib.admin",
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "ldaporm",
        ],
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        },
        SECRET_KEY="test-secret-key-for-admin-tests",
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
                    "follow_referrals": False,
                },
                "write": {
                    "url": "ldap://localhost:389",
                    "user": "cn=admin,dc=example,dc=com",
                    "password": "admin",
                    "use_starttls": False,
                    "tls_verify": "never",
                    "timeout": 15.0,
                    "sizelimit": 1000,
                    "follow_referrals": False,
                },
            }
        },
    )
    try:
        django.setup()
    except Exception:
        pass


class AdminTestUser(Model):
    """Test model for admin integration tests."""

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
        verbose_name = "Test User"
        verbose_name_plural = "Test Users"


class AdminTestGroup(Model):
    """Test group model for admin integration tests."""

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
        verbose_name = "Test Group"
        verbose_name_plural = "Test Groups"


class TestDjangoAdminIntegration(LDAPFakerMixin, unittest.TestCase):
    """Test suite for Django Admin integration with ldaporm models."""

    ldap_modules = ["ldaporm"]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_users = [
            [
                "cn=admin,dc=example,dc=com",
                {
                    "cn": [b"admin"],
                    "userPassword": [b"admin"],
                    "objectclass": [b"simpleSecurityObject", b"organizationalRole", b"top"],
                },
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
                    "objectclass": [b"posixAccount", b"top"],
                },
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
                    "objectclass": [b"posixAccount", b"top"],
                },
            ],
        ]
        cls.test_groups = [
            [
                "cn=developers,ou=groups,dc=example,dc=com",
                {
                    "cn": [b"developers"],
                    "gidNumber": [b"2001"],
                    "memberUid": [b"alice", b"bob"],
                    "objectclass": [b"posixGroup", b"top"],
                },
            ],
        ]

    def setUp(self):
        super().setUp()
        if not hasattr(self, "ldap_faker"):
            LDAPFakerMixin.setUp(self)

        self.settings_patcher = patch(
            "django.conf.settings.LDAP_SERVERS",
            {
                "test_server": {
                    "read": {
                        "url": "ldap://localhost:389",
                        "user": "cn=admin,dc=example,dc=com",
                        "password": "admin",
                        "use_starttls": False,
                        "tls_verify": "never",
                        "timeout": 15.0,
                        "sizelimit": 1000,
                        "follow_referrals": False,
                    },
                    "write": {
                        "url": "ldap://localhost:389",
                        "user": "cn=admin,dc=example,dc=com",
                        "password": "admin",
                        "use_starttls": False,
                        "tls_verify": "never",
                        "timeout": 15.0,
                        "sizelimit": 1000,
                        "follow_referrals": False,
                    },
                },
            },
        )
        self.settings_patcher.start()

        user_manager = LdapManager()
        user_manager.contribute_to_class(AdminTestUser, "objects")
        group_manager = LdapManager()
        group_manager.contribute_to_class(AdminTestGroup, "objects")

        self.server_factory.default.raw_objects.clear()  # type: ignore[attr-defined]
        self.server_factory.default.objects.clear()  # type: ignore[attr-defined]
        for dn, attrs in self.test_users + self.test_groups:
            self.server_factory.default.register_object((dn, attrs))  # type: ignore[attr-defined]

        self.request_factory = RequestFactory()

    def tearDown(self):
        self.settings_patcher.stop()
        if admin.site.is_registered(AdminTestUser):
            admin.site.unregister(AdminTestUser)
        if admin.site.is_registered(AdminTestGroup):
            admin.site.unregister(AdminTestGroup)
        super().tearDown()

    def test_model_admin_instantiation(self):
        """Test that ModelAdmin can be instantiated with an ldaporm model."""
        model_admin = admin.ModelAdmin(AdminTestUser, admin.site)
        self.assertIs(model_admin.model, AdminTestUser)
        self.assertIs(model_admin.model._meta.model, AdminTestUser)

    def test_model_admin_registration(self):
        """Test that ldaporm models can be registered with admin.site."""
        admin.site.register(AdminTestUser, admin.ModelAdmin)
        self.assertTrue(admin.site.is_registered(AdminTestUser))

    def test_model_admin_get_form(self):
        """Test that ModelAdmin can generate a ModelForm for ldaporm models."""
        model_admin = admin.ModelAdmin(AdminTestUser, admin.site)
        form_class = model_admin.get_form(self.request_factory.get("/"))
        self.assertIsNotNone(form_class)
        self.assertEqual(form_class.Meta.model, AdminTestUser)

    def test_model_admin_get_queryset(self):
        """Test that ModelAdmin.get_queryset returns ldaporm queryset."""
        model_admin = admin.ModelAdmin(AdminTestUser, admin.site)
        request = self.request_factory.get("/")
        queryset = model_admin.get_queryset(request)
        self.assertIsNotNone(queryset)
        users = list(queryset)
        self.assertEqual(len(users), 2)
        uids = [u.uid for u in users]
        self.assertIn("alice", uids)
        self.assertIn("bob", uids)

    def test_model_admin_add_form_instantiation(self):
        """Test that ModelAdmin add form can be instantiated with ldaporm model."""
        model_admin = admin.ModelAdmin(AdminTestUser, admin.site)
        form_class = model_admin.get_form(self.request_factory.get("/"))
        form = form_class()
        self.assertIsNotNone(form)
        self.assertEqual(form.Meta.model, AdminTestUser)

    def test_model_admin_list_display(self):
        """Test that ModelAdmin list_display works with ldaporm model fields."""
        model_admin = admin.ModelAdmin(AdminTestUser, admin.site)
        model_admin.list_display = ["uid", "cn", "sn"]
        request = self.request_factory.get("/")
        queryset = model_admin.get_queryset(request)
        users = list(queryset)
        self.assertGreater(len(users), 0)
        for user in users:
            for field_name in model_admin.list_display:
                self.assertTrue(hasattr(user, field_name))

    def test_model_serializable_value(self):
        """Test serializable_value required by Django admin."""
        users = list(AdminTestUser.objects.all())
        self.assertGreater(len(users), 0)
        user = users[0]
        value = user.serializable_value("uid")
        self.assertEqual(value, user.uid)

    def test_model_meta_admin_compatibility(self):
        """Test that model _meta has attributes required by Django admin."""
        meta = AdminTestUser._meta
        self.assertIsNotNone(meta)
        self.assertEqual(meta.verbose_name, "Test User")
        self.assertEqual(meta.verbose_name_plural, "Test Users")
        self.assertIsNotNone(meta.pk)
        self.assertEqual(meta.pk.name, "uid")
        self.assertIsNotNone(meta.fields)
        self.assertGreater(len(meta.fields), 0)

    def test_model_state_for_admin(self):
        """Test that model instances have _state required by Django admin."""
        users = list(AdminTestUser.objects.all())
        self.assertGreater(len(users), 0)
        user = users[0]
        self.assertIsNotNone(user._state)
        self.assertTrue(hasattr(user._state, "adding"))
        self.assertTrue(hasattr(user._state, "db"))
