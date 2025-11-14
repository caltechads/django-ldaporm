"""
LDAP ORM type definitions.

This module provides type aliases for LDAP data structures and operations,
using Python 3.10+ type hinting conventions.
"""

DeleteModListEntry = tuple[int, str, None]
ModifyModListEntry = tuple[int, str, str]
AddModlistEntry = tuple[str, str]
ModifyDeleteModList = list[DeleteModListEntry | ModifyModListEntry | AddModlistEntry]
AddModlist = list[tuple[str, str]]
LDAPData = tuple[str, dict[str, list[bytes]]]
