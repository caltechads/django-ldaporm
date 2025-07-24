Version Compatibility
====================

This page shows the compatibility matrix for django-ldaporm with different versions of Python, Django, and other dependencies.

Python Compatibility
--------------------

django-ldaporm supports the following Python versions:

+----------------+----------------+----------------+----------------+
| django-ldaporm | Python 3.10    | Python 3.11    | Python 3.12    |
+================+================+================+================+
| 1.2.0+         | ✅ Supported   | ✅ Supported   | ✅ Supported   |
+----------------+----------------+----------------+----------------+
| 1.1.x          | ✅ Supported   | ✅ Supported   | ❌ Not tested  |
+----------------+----------------+----------------+----------------+
| 1.0.x          | ✅ Supported   | ❌ Not tested  | ❌ Not tested  |
+----------------+----------------+----------------+----------------+

Django Compatibility
--------------------

django-ldaporm supports the following Django versions:

+----------------+----------------+----------------+----------------+----------------+
| django-ldaporm | Django 4.2     | Django 4.3     | Django 5.0     | Django 5.2     |
+================+================+================+================+================+
| 1.2.0+         | ✅ Supported   | ✅ Supported   | ✅ Supported   | ✅ Supported   |
+----------------+----------------+----------------+----------------+----------------+
| 1.1.x          | ✅ Supported   | ✅ Supported   | ✅ Supported   | ❌ Not tested  |
+----------------+----------------+----------------+----------------+----------------+
| 1.0.x          | ✅ Supported   | ✅ Supported   | ❌ Not tested  | ❌ Not tested  |
+----------------+----------------+----------------+----------------+----------------+

.. note::
   The demo application requires Django 5.2+ for some features.

Dependency Compatibility
------------------------

Core Dependencies
^^^^^^^^^^^^^^^^

+----------------+----------------+----------------+----------------+
| django-ldaporm | python-ldap    | Django         | Python         |
+================+================+================+================+
| 1.2.0+         | 3.4.0+         | 4.2+           | 3.10+          |
+----------------+----------------+----------------+----------------+
| 1.1.x          | 3.4.0+         | 4.2+           | 3.10+          |
+----------------+----------------+----------------+----------------+
| 1.0.x          | 3.4.0+         | 4.2+           | 3.10+          |
+----------------+----------------+----------------+----------------+

Optional Dependencies
^^^^^^^^^^^^^^^^^^^^

+----------------+----------------+----------------+----------------+
| Feature        | Package        | Version        | Required       |
+================+================+================+================+
| REST Framework | djangorestframework | 3.14+     | No             |
+----------------+----------------+----------------+----------------+
| Wildewidgets   | django-wildewidgets | 0.20+    | No             |
+----------------+----------------+----------------+----------------+
| Testing        | pytest         | 7.0+           | No             |
+----------------+----------------+----------------+----------------+
| Development    | black           | 23.0+          | No             |
+----------------+----------------+----------------+----------------+

LDAP Server Compatibility
-------------------------

django-ldaporm has been tested with the following LDAP servers:

+----------------+----------------+----------------+----------------+
| LDAP Server    | Version        | Status         | Notes          |
+================+================+================+================+
| OpenLDAP       | 2.4+           | ✅ Supported   | Primary target |
+----------------+----------------+----------------+----------------+
| Active Directory | 2016+        | ✅ Supported   | AD-specific features |
+----------------+----------------+----------------+----------------+
| Apache DS      | 2.0+           | ✅ Supported   | Full compatibility |
+----------------+----------------+----------------+----------------+
| 389 Directory Server | 1.4+   | ✅ Supported   | Full compatibility |
+----------------+----------------+----------------+----------------+
| FreeIPA        | 4.8+           | ✅ Supported   | Based on 389 DS |
+----------------+----------------+----------------+----------------+
| Samba AD       | 4.0+           | ✅ Supported   | AD-compatible   |
+----------------+----------------+----------------+----------------+

.. note::
   While django-ldaporm should work with most LDAP servers, these are the ones
   that have been specifically tested. If you encounter issues with other LDAP
   servers, please report them.

Feature Compatibility
---------------------

LDAP Features
^^^^^^^^^^^^

+----------------+----------------+----------------+----------------+
| Feature        | OpenLDAP       | Active Directory | Apache DS    |
+================+================+================+================+
| Basic CRUD     | ✅ Full        | ✅ Full         | ✅ Full        |
+----------------+----------------+----------------+----------------+
| Paging         | ✅ Full        | ✅ Full         | ✅ Full        |
+----------------+----------------+----------------+----------------+
| VLV            | ✅ Full        | ❌ Not supported | ✅ Full       |
+----------------+----------------+----------------+----------------+
| Server-side Sorting | ✅ Full  | ❌ Not supported | ✅ Full       |
+----------------+----------------+----------------+----------------+
| TLS/SSL        | ✅ Full        | ✅ Full         | ✅ Full        |
+----------------+----------------+----------------+----------------+
| SASL           | ✅ Full        | ✅ Full         | ✅ Full        |
+----------------+----------------+----------------+----------------+

Django Integration
^^^^^^^^^^^^^^^^^

+----------------+----------------+----------------+----------------+
| Feature        | Django 4.2     | Django 5.0     | Django 5.2     |
+================+================+=================+================+
| Forms          | ✅ Full        | ✅ Full         | ✅ Full         |
+----------------+----------------+----------------+----------------+
| Admin          | ✅ Full        | ✅ Full         | ✅ Full         |
+----------------+----------------+----------------+----------------+
| REST Framework | ✅ Full        | ✅ Full         | ✅ Full         |
+----------------+----------------+----------------+----------------+
| Wildewidgets   | ✅ Full        | ✅ Full         | ✅ Full         |
+----------------+----------------+----------------+----------------+

Migration Guide
---------------

Upgrading from 1.1.x to 1.2.0
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Breaking Changes:**

1. **Paging Configuration**: The ``paged_search`` option in ``Meta.ldap_options`` is deprecated and will be removed in a future version. Paging is now detected automatically based on server capabilities.

2. **Direct Iteration**: You can now iterate over query results directly without calling ``.all()``:
   .. code-block:: python

      # Old way (still works)
      users = User.objects.filter(is_active=True).all()
      for user in users:
          print(user.uid)

      # New way (recommended)
      for user in User.objects.filter(is_active=True):
          print(user.uid)

3. **Slicing**: Query results now support Python slicing and indexing:
   .. code-block:: python

      # Get first 10 users
      first_ten = User.objects.filter(is_active=True)[:10]

      # Get specific user by index
      first_user = User.objects.filter(is_active=True)[0]

**New Features:**

1. **Convenience Methods**: New methods available on managers:
   - ``.count()`` - Efficient counting
   - ``.as_list()`` - Convert to list
   - ``.get_or_none()`` - Get object or None
   - ``.first_or_none()`` - Get first object or None

2. **Automatic Detection**: Server capabilities are now detected automatically:
   - Paging support
   - Server flavor (OpenLDAP, Active Directory, etc.)
   - Page size limits

3. **Django Settings Integration**: Page size limits and cache TTL can be configured via Django settings.

Upgrading from 1.0.x to 1.1.x
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Breaking Changes:**

1. **Python Version**: Minimum Python version increased to 3.10
2. **Django Version**: Minimum Django version increased to 4.2

**New Features:**

1. **Enhanced Active Directory Support**: Improved handling of AD-specific attributes and timestamps
2. **Better Error Handling**: More informative error messages and better exception handling
3. **Performance Improvements**: Optimized query execution and connection management

Testing Your Installation
-------------------------

To verify your installation is compatible, run the test suite:

.. code-block:: bash

   # Install test dependencies
   pip install -e ".[test]"

   # Run tests
   python -m pytest

   # Run with specific Django version
   python -m pytest --django-version=5.2

   # Run with specific Python version
   python3.11 -m pytest

Compatibility Testing
--------------------

The django-ldaporm project maintains a comprehensive test suite that covers:

- Multiple Python versions (3.10, 3.11, 3.12)
- Multiple Django versions (4.2, 4.3, 5.0, 5.2)
- Multiple LDAP servers (OpenLDAP, Active Directory, Apache DS)
- Different LDAP configurations (TLS, SASL, paging, etc.)

Continuous Integration
^^^^^^^^^^^^^^^^^^^^^^

The project uses GitHub Actions to test compatibility with:

- Python 3.10, 3.11, 3.12
- Django 4.2, 4.3, 5.0, 5.2
- Multiple LDAP server types
- Different operating systems (Linux, macOS, Windows)

Reporting Compatibility Issues
-----------------------------

If you encounter compatibility issues:

1. **Check this page** to verify your versions are supported
2. **Enable debug logging** to get detailed error information
3. **Create a minimal test case** to reproduce the issue
4. **Report the issue** with:
   - Python version
   - Django version
   - LDAP server type and version
   - Complete error traceback
   - Minimal code to reproduce the issue

.. note::
   This compatibility matrix is updated with each release. For the most
   current information, check the version you're using or the latest
   release notes.