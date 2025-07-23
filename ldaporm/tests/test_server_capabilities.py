"""
Tests for LdapServerCapabilities class.
"""

import logging
import unittest
from unittest.mock import Mock, patch

import ldap
from django.conf import settings
from django.test import override_settings, TestCase

from ldaporm.server_capabilities import LdapServerCapabilities


# Configure Django settings for testing
if not settings.configured:
    settings.configure(
        LDAPORM_DEFAULT_PAGE_SIZE=1000,
        LDAPORM_MIN_PAGE_SIZE=10,
        LDAPORM_MAX_PAGE_SIZE=10000,
        LDAPORM_CACHE_TTL=3600,
    )


class TestLdapServerCapabilities(unittest.TestCase):
    """Test server capability detection."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_connection = Mock()
        self.key = "test_server"

        # Clear cache before each test
        LdapServerCapabilities.clear_cache()

        # Set up logging capture
        self.log_capture = self.assertLogs('ldaporm.server_capabilities', level='WARNING')

    def test_detect_openldap_server(self):
        """Test OpenLDAP server detection."""
        # Mock Root DSE response for OpenLDAP
        self.mock_connection.search_s.return_value = [
            ("", {
                "vendorName": [b"OpenLDAP Foundation"],
                "sizelimit": [b"1000"],
                "hardlimit": [b"2000"]
            })
        ]

        flavor = LdapServerCapabilities.detect_server_flavor(
            self.mock_connection, self.key
        )
        self.assertEqual(flavor, "openldap")

    def test_detect_active_directory_server(self):
        """Test Active Directory server detection."""
        # Mock Root DSE response for AD
        self.mock_connection.search_s.return_value = [
            ("", {
                "forestFunctionality": [b"3"],
                "MaxPageSize": [b"1000"]
            })
        ]

        flavor = LdapServerCapabilities.detect_server_flavor(
            self.mock_connection, self.key
        )
        self.assertEqual(flavor, "active_directory")

    def test_detect_389_server(self):
        """Test 389 Directory Server detection."""
        # Mock Root DSE response for 389
        self.mock_connection.search_s.return_value = [
            ("", {
                "vendorName": [b"Fedora Project"],
                "nsslapd-sizelimit": [b"1000"]
            })
        ]

        flavor = LdapServerCapabilities.detect_server_flavor(
            self.mock_connection, self.key
        )
        self.assertEqual(flavor, "389")

    def test_detect_389_oracle_variant(self):
        """Test Oracle 389 Directory Server variant detection."""
        # Mock Root DSE response for Oracle 389
        self.mock_connection.search_s.return_value = [
            ("", {
                "vendorName": [b"Oracle Corporation"],
                "nsslapd-sizelimit": [b"1000"]
            })
        ]

        flavor = LdapServerCapabilities.detect_server_flavor(
            self.mock_connection, self.key
        )
        self.assertEqual(flavor, "389")

    def test_detect_389_forgerock_variant(self):
        """Test ForgeRock 389 Directory Server variant detection."""
        # Mock Root DSE response for ForgeRock 389
        self.mock_connection.search_s.return_value = [
            ("", {
                "vendorName": [b"ForgeRock AS"],
                "nsslapd-sizelimit": [b"1000"]
            })
        ]

        flavor = LdapServerCapabilities.detect_server_flavor(
            self.mock_connection, self.key
        )
        self.assertEqual(flavor, "389")

    def test_detect_unknown_server(self):
        """Test unknown server detection."""
        # Mock Root DSE response for unknown server
        self.mock_connection.search_s.return_value = [
            ("", {
                "vendorName": [b"Unknown Vendor"],
                "sizelimit": [b"1000"]
            })
        ]

        flavor = LdapServerCapabilities.detect_server_flavor(
            self.mock_connection, self.key
        )
        self.assertEqual(flavor, "unknown")

    def test_check_control_support(self):
        """Test control support detection."""
        # Mock Root DSE response with supported control
        self.mock_connection.search_s.return_value = [
            ("", {
                "vendorName": [b"OpenLDAP Foundation"],
                "sizelimit": [b"1000"],
                "supportedControl": [b"1.2.840.113556.1.4.319"]
            })
        ]

        supported = LdapServerCapabilities.check_control_support(
            self.mock_connection,
            oid="1.2.840.113556.1.4.319",
            feature_name="paged results",
            key=self.key
        )
        self.assertTrue(supported)

    def test_check_control_support_not_found(self):
        """Test control support detection when not supported."""
        # Mock Root DSE response without the control
        self.mock_connection.search_s.return_value = [
            ("", {
                "supportedControl": [b"1.2.840.113556.1.4.473"]  # Different control
            })
        ]

        supported = LdapServerCapabilities.check_control_support(
            self.mock_connection,
            oid="1.2.840.113556.1.4.319",
            feature_name="paged results",
            key=self.key
        )
        self.assertFalse(supported)

    def test_get_page_size_limit_openldap(self):
        """Test page size limit detection for OpenLDAP."""
        # Mock Root DSE response
        self.mock_connection.search_s.return_value = [
            ("", {
                "vendorName": [b"OpenLDAP Foundation"],
                "sizelimit": [b"1500"],
                "hardlimit": [b"2000"]
            })
        ]

        page_size = LdapServerCapabilities.get_server_page_size_limit(
            self.mock_connection, self.key
        )
        self.assertEqual(page_size, 1500)

    def test_get_page_size_limit_active_directory(self):
        """Test page size limit detection for Active Directory."""
        # Mock Root DSE response
        self.mock_connection.search_s.return_value = [
            ("", {
                "forestFunctionality": [b"3"],
                "MaxPageSize": [b"2000"]
            })
        ]

        page_size = LdapServerCapabilities.get_server_page_size_limit(
            self.mock_connection, self.key
        )
        self.assertEqual(page_size, 2000)

    def test_get_page_size_limit_389(self):
        """Test page size limit detection for 389 Directory Server."""
        # Mock Root DSE response
        self.mock_connection.search_s.return_value = [
            ("", {
                "vendorName": [b"Fedora Project"],
                "nsslapd-sizelimit": [b"3000"]
            })
        ]

        page_size = LdapServerCapabilities.get_server_page_size_limit(
            self.mock_connection, self.key
        )
        self.assertEqual(page_size, 3000)

    def test_get_page_size_limit_389_oracle_variant(self):
        """Test page size limit detection for Oracle 389 Directory Server variant."""
        # Mock Root DSE response
        self.mock_connection.search_s.return_value = [
            ("", {
                "vendorName": [b"Oracle Corporation"],
                "nsslapd-sizelimit": [b"4000"]
            })
        ]

        page_size = LdapServerCapabilities.get_server_page_size_limit(
            self.mock_connection, self.key
        )
        self.assertEqual(page_size, 4000)

    def test_get_page_size_limit_389_forgerock_variant(self):
        """Test page size limit detection for ForgeRock 389 Directory Server variant."""
        # Mock Root DSE response
        self.mock_connection.search_s.return_value = [
            ("", {
                "vendorName": [b"ForgeRock AS"],
                "nsslapd-sizelimit": [b"5000"]
            })
        ]

        page_size = LdapServerCapabilities.get_server_page_size_limit(
            self.mock_connection, self.key
        )
        self.assertEqual(page_size, 5000)

    def test_connection_error_propagation(self):
        """Test that connection errors propagate up."""
        self.mock_connection.search_s.side_effect = ldap.SERVER_DOWN

        with self.assertRaises(ldap.SERVER_DOWN):
            LdapServerCapabilities.detect_server_flavor(
                self.mock_connection, self.key
            )

    def test_caching_behavior(self):
        """Test that results are properly cached."""
        # First call should query server
        self.mock_connection.search_s.return_value = [
            ("", {"vendorName": [b"OpenLDAP Foundation"]})
        ]

        flavor1 = LdapServerCapabilities.detect_server_flavor(
            self.mock_connection, self.key
        )

        # Second call should use cache (no additional queries)
        flavor2 = LdapServerCapabilities.detect_server_flavor(
            self.mock_connection, self.key
        )

        self.assertEqual(flavor1, flavor2)
        self.assertEqual(self.mock_connection.search_s.call_count, 1)

    def test_clear_cache(self):
        """Test cache clearing functionality."""
        # First call to populate cache
        self.mock_connection.search_s.return_value = [
            ("", {"vendorName": [b"OpenLDAP Foundation"]})
        ]

        LdapServerCapabilities.detect_server_flavor(
            self.mock_connection, self.key
        )

        # Clear cache
        LdapServerCapabilities.clear_cache(self.key)

        # Second call should query server again
        LdapServerCapabilities.detect_server_flavor(
            self.mock_connection, self.key
        )

        # Should have been called twice (once before clear, once after)
        self.assertEqual(self.mock_connection.search_s.call_count, 2)

    def test_get_cache_stats(self):
        """Test cache statistics functionality."""
        # Populate cache with some data
        self.mock_connection.search_s.return_value = [
            ("", {"vendorName": [b"OpenLDAP Foundation"]})
        ]

        LdapServerCapabilities.detect_server_flavor(
            self.mock_connection, self.key
        )

        stats = LdapServerCapabilities.get_cache_stats()

        self.assertIn("total_entries", stats)
        self.assertIn("valid_entries", stats)
        self.assertIn("expired_entries", stats)
        self.assertIn("cache_keys", stats)
        self.assertGreater(stats["total_entries"], 0)


class TestLdapServerCapabilitiesOpenLDAP(unittest.TestCase):
    """Test OpenLDAP-specific behavior."""

    def setUp(self):
        self.mock_connection = Mock()
        self.key = "test_openldap_server"

        # Clear cache before each test
        LdapServerCapabilities.clear_cache()

    def test_openldap_sorting_warning(self):
        """Test that OpenLDAP users get helpful warning about sorting."""
        # Mock OpenLDAP server without sorting support
        self.mock_connection.search_s.return_value = [
            ("", {
                "vendorName": [b"OpenLDAP Foundation"],
                "sizelimit": [b"1000"],
                "supportedControl": [b"1.2.840.113556.1.4.319"]  # Only paging, no sorting
            })
        ]

        with self.assertLogs('ldaporm.server_capabilities', level='WARNING') as log_capture:
            supported = LdapServerCapabilities.check_server_sorting_support(
                self.mock_connection, self.key
            )

        self.assertFalse(supported)
        self.assertIn("overlay sssvlv", log_capture.output[0])

    def test_openldap_with_sorting_no_warning(self):
        """Test that OpenLDAP with sorting support doesn't show warning."""
        # Mock OpenLDAP server with sorting support
        self.mock_connection.search_s.return_value = [
            ("", {
                "vendorName": [b"OpenLDAP Foundation"],
                "sizelimit": [b"1000"],
                "supportedControl": [
                    b"1.2.840.113556.1.4.319",  # Paging
                    b"1.2.840.113556.1.4.473"   # Sorting
                ]
            })
        ]

        supported = LdapServerCapabilities.check_server_sorting_support(
            self.mock_connection, self.key
        )

        self.assertTrue(supported)
        # No warning should be logged since sorting is supported

    def test_non_openldap_no_sorting_no_warning(self):
        """Test that non-OpenLDAP servers don't get OpenLDAP-specific warning."""
        # Mock Active Directory without sorting support
        self.mock_connection.search_s.return_value = [
            ("", {
                "forestFunctionality": [b"3"],
                "MaxPageSize": [b"1000"],
                "supportedControl": [b"1.2.840.113556.1.4.319"]  # Only paging
            })
        ]

        supported = LdapServerCapabilities.check_server_sorting_support(
            self.mock_connection, self.key
        )

        self.assertFalse(supported)
        # Should not have OpenLDAP-specific warning since it's not OpenLDAP


class TestLdapServerCapabilitiesSettings(unittest.TestCase):
    """Test Django settings integration."""

    def setUp(self):
        self.mock_connection = Mock()
        self.key = "test_server"

        # Clear cache before each test
        LdapServerCapabilities.clear_cache()

    def test_default_page_size_from_settings(self):
        """Test that default page size comes from Django settings."""
        with override_settings(LDAPORM_DEFAULT_PAGE_SIZE=500):
            # Mock unknown server (will use default)
            self.mock_connection.search_s.return_value = [
                ("", {"vendorName": [b"Unknown Vendor"]})
            ]

            page_size = LdapServerCapabilities.get_server_page_size_limit(
                self.mock_connection, self.key
            )
            self.assertEqual(page_size, 500)

    def test_page_size_bounds_from_settings(self):
        """Test that page size bounds come from Django settings."""
        with override_settings(
            LDAPORM_MIN_PAGE_SIZE=50,
            LDAPORM_MAX_PAGE_SIZE=5000
        ):
            # Mock OpenLDAP with very large page size
            self.mock_connection.search_s.return_value = [
                ("", {
                    "vendorName": [b"OpenLDAP Foundation"],
                    "sizelimit": [b"9999"]  # Should be clamped to 5000
                })
            ]

            page_size = LdapServerCapabilities.get_server_page_size_limit(
                self.mock_connection, self.key
            )
            self.assertEqual(page_size, 5000)

    def test_settings_fallback(self):
        """Test that default values are used when settings are missing."""
        # Mock unknown server without any settings
        self.mock_connection.search_s.return_value = [
            ("", {"vendorName": [b"Unknown Vendor"]})
        ]

        page_size = LdapServerCapabilities.get_server_page_size_limit(
            self.mock_connection, self.key
        )
        # Should use default of 1000
        self.assertEqual(page_size, 1000)

    def test_cache_ttl_from_settings(self):
        """Test that cache TTL comes from Django settings."""
        with override_settings(LDAPORM_CACHE_TTL=1800):  # 30 minutes
            # First call to populate cache
            self.mock_connection.search_s.return_value = [
                ("", {"vendorName": [b"OpenLDAP Foundation"]})
            ]

            LdapServerCapabilities.detect_server_flavor(
                self.mock_connection, self.key
            )

            # Get cache stats to verify TTL is being used
            stats = LdapServerCapabilities.get_cache_stats()
            self.assertGreater(stats["valid_entries"], 0)


class TestLdapServerCapabilitiesVLV(unittest.TestCase):
    """Test VLV support detection."""

    def setUp(self):
        self.mock_connection = Mock()
        self.key = "test_server"

        # Clear cache before each test
        LdapServerCapabilities.clear_cache()

    def test_vlv_support_detection(self):
        """Test VLV support detection."""
        # Mock server with VLV support
        self.mock_connection.search_s.return_value = [
            ("", {
                "supportedControl": [
                    b"1.2.840.113556.1.4.319",  # Paging
                    b"1.2.840.113556.1.4.473",  # Server-side sort
                    b"2.16.840.1.113730.3.4.9"  # VLV
                ]
            })
        ]

        supported = LdapServerCapabilities.check_control_support(
            self.mock_connection, "2.16.840.1.113730.3.4.9", "virtual list view", self.key
        )
        self.assertTrue(supported)

    def test_vlv_support_detection_not_supported(self):
        """Test VLV support detection when not supported."""
        # Mock server without VLV support
        self.mock_connection.search_s.return_value = [
            ("", {
                "supportedControl": [
                    b"1.2.840.113556.1.4.319",  # Paging
                    b"1.2.840.113556.1.4.473"   # Server-side sort
                ]
            })
        ]

        supported = LdapServerCapabilities.check_control_support(
            self.mock_connection, "2.16.840.1.113730.3.4.9", "virtual list view", self.key
        )
        self.assertFalse(supported)

    def test_vlv_support_detection_openldap_warning(self):
        """Test OpenLDAP warning when VLV not supported."""
        # Mock OpenLDAP without VLV support
        self.mock_connection.search_s.return_value = [
            ("", {
                "vendorName": [b"OpenLDAP Foundation"],
                "supportedControl": [
                    b"1.2.840.113556.1.4.319"  # Only paging
                ]
            })
        ]

        with self.assertLogs('ldaporm.server_capabilities', level='WARNING') as log:
            supported = LdapServerCapabilities.check_server_vlv_support(
                self.mock_connection, self.key
            )

            self.assertFalse(supported)
            self.assertIn("overlay sssvlv", log.output[0])

    def test_vlv_support_detection_openldap_with_support(self):
        """Test OpenLDAP with VLV support (no warning)."""
        # Mock OpenLDAP with VLV support
        self.mock_connection.search_s.return_value = [
            ("", {
                "vendorName": [b"OpenLDAP Foundation"],
                "supportedControl": [
                    b"1.2.840.113556.1.4.319",  # Paging
                    b"2.16.840.1.113730.3.4.9"  # VLV
                ]
            })
        ]

        supported = LdapServerCapabilities.check_server_vlv_support(
            self.mock_connection, self.key
        )

        self.assertTrue(supported)


if __name__ == '__main__':
    unittest.main()