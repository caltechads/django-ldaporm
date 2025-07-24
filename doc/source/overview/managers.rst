Managers Guide
==============

This guide covers using :py:class:`~ldaporm.managers.LdapManager` and its
subclasses to query and manipulate LDAP data. For complete API documentation,
see :doc:`../api/managers`.

Overview
--------

:py:class:`~ldaporm.managers.LdapManager` provides a Django QuerySet-like
interface for LDAP operations.  It handles LDAP searches, filtering, and CRUD
operations while maintaining a familiar Django API.

All models automatically have their ``objects`` attribute set to an instance of
:py:class:`~ldaporm.managers.LdapManager`, but you can override this by
setting the ``objects`` attribute to an instance of a subclass of
:py:class:`~ldaporm.managers.LdapManager`.

What's New (2025)
-----------------

- **Direct Iteration:** You can now iterate over query results directly, without needing to call ``.all()``.
- **Slicing and Indexing:** Query results support Python slicing and indexing. Slicing with ``[:stop]`` is efficient; other slices fetch all results then slice in Python.
- **Convenience Methods:** ``.count()``, ``.as_list()``, ``.get_or_none()``, and ``.first_or_none()`` are available on both F and LdapManager objects.
- **LDAP Paging:** New ``.page()`` method and ``LdapCursorPagination`` for efficient server-side paging of large result sets.
- **Automatic Server-Side Sorting:** ``.order_by()`` method will use Server Side Sorting (OID: 20030802.1.1.1.1) for server-side sorting of large result sets, if available.
- **Virtual List View (VLV):** Automatic VLV support for efficient slicing of large result sets with fallback to client-side slicing.
- **Automatic Paging Detection:** Paging is now detected automatically based on server capabilities.
- **Automatic Server Flavor Detection:** Server flavor is now detected automatically based on server capabilities.
- **Automatic page size detection:** Page size is now detected automatically based on server capabilities.
- **Django Settings Integration:** Page size limits and cache TTL can be configured via Django settings.
- **Backward Compatibility:** ``.all()`` is still supported and works as before.

.. deprecated:: 2025

   The ``paged_search`` option in ``Meta.ldap_options`` is deprecated and will be removed
   in a future version. Paging is now detected automatically based on server capabilities.

Basic Querying
--------------

Direct Iteration
^^^^^^^^^^^^^^^

You can now iterate over query results directly:

.. code-block:: python

   # Direct iteration (no .all() needed)
   for user in User.objects.filter(is_active=True):
       print(user.uid)

   # Indexing
   first_user = User.objects.filter(is_active=True)[0]

   # Efficient slicing (uses VLV if supported, otherwise client-side)
   first_ten = User.objects.filter(is_active=True)[:10]

   # Efficient slicing (uses VLV if supported, otherwise client-side)
   middle_five = User.objects.filter(is_active=True)[5:10]

.. note::
   You can still use ``.all()`` for backward compatibility:

   .. code-block:: python

      users = User.objects.filter(is_active=True).all()

.. note::
   Slicing operations (e.g., ``[10:20]``) automatically use Virtual List View (VLV)
   when supported by the LDAP server, providing efficient server-side slicing.
   When VLV is not supported, slicing falls back to client-side operations.
   See :doc:`vlv` for more details.

Convenience Methods
^^^^^^^^^^^^^^^^^^^

New convenience methods for common operations:

.. code-block:: python

   # Count
   num_active = User.objects.filter(is_active=True).count()

   # as_list
   user_list = User.objects.filter(is_active=True).as_list()

   # get_or_none
   user = User.objects.get_or_none(uid='john.doe')

   # first_or_none
   user = User.objects.filter(is_active=True).first_or_none()

LDAP Paging
^^^^^^^^^^^

Efficient server-side paging for large result sets:

.. code-block:: python

   # LDAP paging
   paged_results = User.objects.filter(is_active=True).page(page_size=50)
   for user in paged_results:
       print(user.uid)
   if paged_results.has_more:
       next_page = User.objects.filter(is_active=True).page(
           page_size=50, cookie=paged_results.next_cookie
       )

Subclassing
-----------

You can subclass :py:class:`~ldaporm.managers.LdapManager` to add custom
methods to your manager.  For example you can add new methods to your manager
to do common operations on your LDAP objects.

.. code-block:: python

   from datetime import datetime
   from ldaporm.managers import LdapManager

   class UserManager(LdapManager):
       def active_users(self):
           """Return only active users."""
           return self.filter(is_active=True)

       def users_by_department(self, department):
           """Return users in a specific department."""
           return self.filter(department=department)

       def recently_created(self, days=30):
           """Return users created in the last N days."""
           cutoff_date = datetime.now() - timedelta(days=days)
           return self.filter(created__gte=cutoff_date)

   class User(Model):
       uid = CharField('uid', primary_key=True, max_length=50)
       cn = CharField('cn', max_length=100)
       department = CharField('department', max_length=100, blank=True)
       is_active = BooleanField('userAccountControl', default=True)
       created = DateTimeField('whenCreated', auto_now_add=True)

       objects = UserManager()

       class Meta:
            ...

   # Usage
   active_users = User.objects.active_users()
   dev_users = User.objects.users_by_department('Development')
   recent_users = User.objects.recently_created(days=7)