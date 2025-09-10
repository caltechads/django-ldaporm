"""
LDAP server capability detection and caching.

This module provides the LdapServerCapabilities class for detecting
server flavors, supported controls, and server-specific limits.
"""

import logging
import threading
import time
from typing import Any, ClassVar

import ldap
from django.conf import settings

logger = logging.getLogger(__name__)


class LdapServerCapabilities:
    """
    Handles detection and caching of LDAP server capabilities.

    This class provides class methods for detecting server flavors, supported controls,
    and server-specific limits. It uses the connection provided by LdapManager.
    """

    #: Class-level cache for server information per server configuration
    _server_cache: ClassVar[dict[str, dict[str, Any]]] = {}
    #: Thread lock for cache access
    _lock = threading.Lock()

    # Constants for known controls
    SORTING_OID = "1.2.840.113556.1.4.473"
    PAGING_OID = "1.2.840.113556.1.4.319"
    VLV_OID = "2.16.840.1.113730.3.4.9"

    # Cache structure:
    # {
    #   server_key: {
    #     "root_dse": dict,           # Raw Root DSE response
    #     "flavor": str,              # "openldap", "active_directory", "389", "unknown"
    #     "page_size": int,           # Maximum page size
    #     "capabilities": dict,       # {feature_name: bool}
    #     "logged_features": set,     # Features already logged
    #     "cached_at": float          # Timestamp for TTL checking
    #   }
    # }

    @classmethod
    def _get_config(cls, setting_name: str, default_value: Any) -> Any:
        """
        Get configuration value from Django settings with fallback.

        Args:
            setting_name: Name of the setting (without LDAPORM_ prefix)
            default_value: Default value if setting not found

        Returns:
            Configuration value from settings or default

        """
        full_setting_name = f"LDAPORM_{setting_name}"
        return getattr(settings, full_setting_name, default_value)

    @classmethod
    def _get_default_page_size(cls) -> int:
        """Get default page size from settings or use fallback."""
        return cls._get_config("DEFAULT_PAGE_SIZE", 1000)

    @classmethod
    def _get_min_page_size(cls) -> int:
        """Get minimum page size from settings or use fallback."""
        return cls._get_config("MIN_PAGE_SIZE", 10)

    @classmethod
    def _get_max_page_size(cls) -> int:
        """Get maximum page size from settings or use fallback."""
        return cls._get_config("MAX_PAGE_SIZE", 10000)

    @classmethod
    def _get_cache_ttl(cls) -> int:
        """Get cache TTL from settings or use fallback."""
        return cls._get_config("CACHE_TTL", 3600)  # 1 hour default

    @classmethod
    def _get_vlv_context_ttl(cls) -> int:
        """Get VLV context TTL from settings or use fallback."""
        return cls._get_config("VLV_CONTEXT_TTL", 60)  # 60 seconds default

    @classmethod
    def _get_vlv_default_before_count(cls) -> int:
        """Get VLV default before count from settings or use fallback."""
        return cls._get_config("VLV_DEFAULT_BEFORE_COUNT", 0)

    @classmethod
    def _get_vlv_default_after_count(cls) -> int:
        """Get VLV default after count from settings or use fallback."""
        return cls._get_config("VLV_DEFAULT_AFTER_COUNT", 0)

    @classmethod
    def _validate_settings(cls) -> None:
        """
        Validate Django settings for consistency.

        Raises:
            ImproperlyConfigured: If settings are invalid

        """
        from django.core.exceptions import ImproperlyConfigured

        min_size = cls._get_min_page_size()
        max_size = cls._get_max_page_size()
        default_size = cls._get_default_page_size()

        if min_size > max_size:
            msg = (
                f"LDAPORM_MIN_PAGE_SIZE ({min_size}) cannot be greater than "
                f"LDAPORM_MAX_PAGE_SIZE ({max_size})"
            )
            raise ImproperlyConfigured(msg)

        if default_size < min_size or default_size > max_size:
            msg = (
                f"LDAPORM_DEFAULT_PAGE_SIZE ({default_size}) must be between "
                f"LDAPORM_MIN_PAGE_SIZE ({min_size}) and "
                f"LDAPORM_MAX_PAGE_SIZE ({max_size})"
            )
            raise ImproperlyConfigured(msg)

        ttl = cls._get_cache_ttl()
        if ttl <= 0:
            msg = f"LDAPORM_CACHE_TTL ({ttl}) must be positive"
            raise ImproperlyConfigured(msg)

        vlv_ttl = cls._get_vlv_context_ttl()
        if vlv_ttl <= 0:
            msg = f"LDAPORM_VLV_CONTEXT_TTL ({vlv_ttl}) must be positive"
            raise ImproperlyConfigured(msg)

    @classmethod
    def _get_cache_key(cls, connection: Any, key: str) -> str:  # noqa: ARG003
        """Generate cache key based on connection and configuration."""
        # For now, use the key as cache key
        # In the future, could include connection parameters
        return key

    @classmethod
    def _is_cache_valid(cls, cached_info: dict[str, Any]) -> bool:
        """
        Check if cached information is still valid based on TTL.

        Args:
            cached_info: Cached server information

        Returns:
            True if cache is still valid, False otherwise

        """
        if "cached_at" not in cached_info:
            return False

        ttl = cls._get_cache_ttl()
        return (time.time() - cached_info["cached_at"]) < ttl

    @classmethod
    def _get_server_info(cls, connection: Any, key: str = "read") -> dict[str, Any]:
        """
        Get server information from Root DSE, querying only once per server.

        Args:
            connection: LDAP connection from LdapManager
            key: Configuration key for the LDAP server

        Returns:
            Cached server information dictionary

        Raises:
            ldap.SERVER_DOWN, ldap.CONNECT_ERROR: Propagated up

        """
        with cls._lock:
            cache_key = cls._get_cache_key(connection, key)

            # Check cache with TTL
            if cache_key in cls._server_cache:
                cached_info = cls._server_cache[cache_key]
                if cls._is_cache_valid(cached_info):
                    return cached_info

            # Query Root DSE once for all needed information
            try:
                result = connection.search_s(
                    "",  # Root DSE
                    ldap.SCOPE_BASE,
                    "(objectClass=*)",
                    [
                        "vendorName",
                        "forestFunctionality",
                        "sizelimit",
                        "hardlimit",
                        "MaxPageSize",
                        "nsslapd-sizelimit",
                        "supportedControl",
                    ],
                )
            except ldap.LDAPError as e:
                # Only catch non-connection errors
                if isinstance(e, (ldap.SERVER_DOWN, ldap.CONNECT_ERROR)):
                    raise
                # Handle other LDAP errors gracefully
                cls._log_ldap_error(e, "querying Root DSE", key)
                return cls._get_default_server_info()

            if not result:
                return cls._get_default_server_info()

            root_dse_attrs = result[0][1]
            server_info = cls._parse_server_info(root_dse_attrs)

            # Add timestamp for TTL checking
            server_info["cached_at"] = time.time()

            # Cache the result
            cls._server_cache[cache_key] = server_info
            return server_info

    @classmethod
    def _parse_server_info(cls, root_dse_attrs: dict[str, Any]) -> dict[str, Any]:
        """
        Parse Root DSE attributes to determine server capabilities.

        Args:
            root_dse_attrs: Raw Root DSE attributes

        Returns:
            Parsed server information dictionary

        """
        # Detect server flavor with priority ordering
        flavor = cls._detect_server_flavor(root_dse_attrs)

        # Determine page size based on flavor
        page_size = cls._determine_page_size(flavor, root_dse_attrs)

        # Extract supported controls
        supported_controls = root_dse_attrs.get("supportedControl", [])
        control_oids = {control.decode("utf-8") for control in supported_controls}

        return {
            "root_dse": root_dse_attrs,
            "flavor": flavor,
            "page_size": page_size,
            "capabilities": {
                "server-side sorting": cls.SORTING_OID in control_oids,
                "paged results": cls.PAGING_OID in control_oids,
                "virtual_list_view": cls.VLV_OID in control_oids,
            },
            "logged_features": set(),
        }

    @classmethod
    def _detect_server_flavor(cls, root_dse_attrs: dict[str, Any]) -> str:
        """
        Detect server flavor with priority ordering.

        Priority:
        1. Active Directory (forestFunctionality is definitive)
        2. 389 Directory Server (vendor name + specific attributes)
           - Fedora Project (upstream 389)
           - Red Hat (Red Hat Directory Server)
           - Oracle (Oracle Directory Server)
           - ForgeRock (ForgeRock Directory Services)
        3. OpenLDAP (vendor name + specific attributes)
        4. Unknown (fallback)
        """
        # Active Directory detection (highest priority)
        if "forestFunctionality" in root_dse_attrs:
            return "active_directory"

        vendor_names = root_dse_attrs.get("vendorName", [])
        if not vendor_names:
            return "unknown"

        vendor_name = vendor_names[0].decode("utf-8", errors="ignore")

        # 389 Directory Server detection
        if (
            "Fedora Project" in vendor_name
            or "Red Hat" in vendor_name
            or "Oracle" in vendor_name
            or "ForgeRock" in vendor_name
            or "389" in vendor_name
        ):
            return "389"

        # OpenLDAP detection
        if "OpenLDAP Foundation" in vendor_name:
            return "openldap"

        return vendor_name

    @classmethod
    def _determine_page_size(cls, flavor: str, root_dse_attrs: dict[str, Any]) -> int:
        """
        Determine page size with validation and bounds checking.

        Args:
            flavor: Detected server flavor
            root_dse_attrs: Root DSE attributes

        Returns:
            Validated page size (bounded by Django settings)

        """
        try:
            if flavor == "active_directory":
                size_str = root_dse_attrs.get("MaxPageSize", [b"1000"])[0]
            elif flavor == "389":
                size_str = root_dse_attrs.get("nsslapd-sizelimit", [b"1000"])[0]
            elif flavor == "openldap":
                size_str = root_dse_attrs.get("sizelimit", [b"1000"])[0]
            else:
                return cls._get_default_page_size()  # Use Django setting

            page_size = int(size_str.decode("utf-8"))
            return cls._validate_page_size(page_size)

        except (ValueError, UnicodeDecodeError, IndexError):
            # Handle malformed values gracefully
            return cls._get_default_page_size()  # Use Django setting

    @classmethod
    def _validate_page_size(cls, size: int) -> int:
        """
        Validate and bound page size values using Django settings.

        Args:
            size: Raw page size value

        Returns:
            Validated page size within bounds from settings

        """
        min_size = cls._get_min_page_size()
        max_size = cls._get_max_page_size()

        if size < min_size:
            return min_size
        if size > max_size:
            return max_size
        return size

    @classmethod
    def _get_default_server_info(cls) -> dict[str, Any]:
        """Return default server information for unknown servers."""
        return {
            "root_dse": {},
            "flavor": "unknown",
            "page_size": cls._get_default_page_size(),  # Use Django setting
            "capabilities": {
                "server-side sorting": False,
                "paged results": False,
                "virtual_list_view": False,
            },
            "logged_features": set(),
            "cached_at": time.time(),
        }

    @classmethod
    def _log_ldap_error(cls, error: ldap.LDAPError, context: str, key: str) -> None:
        """Enhanced error logging with context."""
        logger.warning("LDAP error while %s for server '%s': %s", context, key, error)

    @classmethod
    def _log_capability_detection(cls, key: str, feature_name: str) -> None:
        """Log capability detection once per feature per server."""
        with cls._lock:
            if key not in cls._server_cache:
                return

            if feature_name not in cls._server_cache[key]["logged_features"]:
                logger.info(
                    "LDAP server '%s' supports %s. Will use server-side %s.",
                    key,
                    feature_name,
                    feature_name,
                )
                cls._server_cache[key]["logged_features"].add(feature_name)

    @classmethod
    def _log_openldap_sorting_warning(cls, key: str) -> None:
        """
        Log a helpful warning for OpenLDAP users about enabling server-side sorting.

        Args:
            key: Configuration key for the LDAP server

        """
        logger.warning(
            "OpenLDAP server '%s' does not support server-side sorting. "
            "To enable server-side sorting, add 'overlay sssvlv' to your OpenLDAP "
            "configuration (slapd.conf) or add the following to your cn=config: "
            "dn: olcOverlay=sssvlv,olcDatabase={1}mdb,cn=config "
            "objectClass: olcOverlayConfig "
            "objectClass: olcSssVlvConfig "
            "olcOverlay: sssvlv",
            key,
        )

    @classmethod
    def _log_openldap_vlv_warning(cls, key: str) -> None:
        """
        Log a helpful warning for OpenLDAP users about enabling server-side VLV.

        Args:
            key: Configuration key for the LDAP server

        """
        logger.warning(
            "OpenLDAP server '%s' does not support server-side Virtual List View. "
            "To enable server-side Virtual List View, add 'overlay sssvlv' to your "
            "OpenLDAP configuration (slapd.conf) or add the following to your "
            "cn=config: dn: olcOverlay=sssvlv,olcDatabase={1}mdb,cn=config "
            "objectClass: olcOverlayConfig "
            "objectClass: olcSssVlvConfig "
            "olcOverlay: sssvlv",
            key,
        )

    @classmethod
    def check_control_support(
        cls, connection: Any, oid: str, feature_name: str, key: str = "read"
    ) -> bool:
        """
        Check if server supports a specific control.

        Args:
            connection: LDAP connection from LdapManager
            oid: Control OID to check
            feature_name: Human-readable feature name for logging
            key: Configuration key for the LDAP server

        Returns:
            True if control is supported, False otherwise

        Raises:
            ldap.SERVER_DOWN, ldap.CONNECT_ERROR: Propagated up

        """
        server_info = cls._get_server_info(connection, key)

        # Check if this specific OID is supported
        supported_controls = server_info["root_dse"].get("supportedControl", [])
        is_supported = any(
            control.decode("utf-8") == oid for control in supported_controls
        )

        # Log detection if supported
        if is_supported:
            cls._log_capability_detection(key, feature_name)

        return is_supported

    @classmethod
    def check_server_sorting_support(cls, connection: Any, key: str = "read") -> bool:
        """
        Check if server supports server-side sorting.

        Args:
            connection: LDAP connection from LdapManager
            key: Configuration key for the LDAP server

        Returns:
            True if server-side sorting is supported, False otherwise

        Raises:
            ldap.SERVER_DOWN, ldap.CONNECT_ERROR: Propagated up

        """
        server_info = cls._get_server_info(connection, key)
        server_flavor = server_info["flavor"]

        # Check if sorting is supported
        is_supported = cls.check_control_support(
            connection, cls.SORTING_OID, feature_name="server-side sorting", key=key
        )

        # Log specific warning for OpenLDAP without sorting support
        if not is_supported and server_flavor == "openldap":
            cls._log_openldap_sorting_warning(key)

        return is_supported

    @classmethod
    def check_server_paging_support(cls, connection: Any, key: str = "read") -> bool:
        """
        Check if server supports paged results.

        Args:
            connection: LDAP connection from LdapManager
            key: Configuration key for the LDAP server

        Returns:
            True if paged results are supported, False otherwise

        Raises:
            ldap.SERVER_DOWN, ldap.CONNECT_ERROR: Propagated up

        """
        return cls.check_control_support(
            connection, cls.PAGING_OID, feature_name="paged results", key=key
        )

    @classmethod
    def check_server_vlv_support(cls, connection: Any, key: str = "read") -> bool:
        """
        Check if server supports Virtual List View.

        Args:
            connection: LDAP connection from LdapManager
            key: Configuration key for the LDAP server

        Returns:
            True if Virtual List View is supported, False otherwise

        Raises:
            ldap.SERVER_DOWN, ldap.CONNECT_ERROR: Propagated up

        """
        server_info = cls._get_server_info(connection, key)
        server_flavor = server_info["flavor"]

        # Check if VLV is supported
        is_supported = cls.check_control_support(
            connection, cls.VLV_OID, feature_name="virtual list view", key=key
        )

        # Log specific warning for OpenLDAP without VLV support
        if not is_supported and server_flavor == "openldap":
            cls._log_openldap_vlv_warning(key)

        return is_supported

    @classmethod
    def get_server_page_size_limit(cls, connection: Any, key: str = "read") -> int:
        """
        Get maximum page size supported by the server.

        Args:
            connection: LDAP connection from LdapManager
            key: Configuration key for the LDAP server

        Returns:
            Maximum page size (bounded by Django settings)

        Raises:
            ldap.SERVER_DOWN, ldap.CONNECT_ERROR: Propagated up

        """
        server_info = cls._get_server_info(connection, key)
        return server_info["page_size"]

    @classmethod
    def detect_server_flavor(cls, connection: Any, key: str = "read") -> str:
        """
        Detect LDAP server flavor.

        Args:
            connection: LDAP connection from LdapManager
            key: Configuration key for the LDAP server

        Returns:
            Server flavor: "openldap", "active_directory", "389", or "unknown"

        Raises:
            ldap.SERVER_DOWN, ldap.CONNECT_ERROR: Propagated up

        """
        server_info = cls._get_server_info(connection, key)
        return server_info["flavor"]

    @classmethod
    def clear_cache(cls, key: str | None = None) -> None:
        """
        Clear cache for specific key or all keys.

        Args:
            key: Configuration key to clear, or None to clear all

        """
        with cls._lock:
            if key is None:
                cls._server_cache.clear()
            else:
                cls._server_cache.pop(key, None)

    @classmethod
    def get_cache_stats(cls) -> dict[str, Any]:
        """
        Get cache statistics for monitoring.

        Returns:
            Dictionary with cache statistics

        """
        with cls._lock:
            total_entries = len(cls._server_cache)
            valid_entries = sum(
                1 for info in cls._server_cache.values() if cls._is_cache_valid(info)
            )

            return {
                "total_entries": total_entries,
                "valid_entries": valid_entries,
                "expired_entries": total_entries - valid_entries,
                "cache_keys": list(cls._server_cache.keys()),
            }
