Managers Guide
=============

This guide covers using :py:class:`~ldaporm.managers.LdapManager` and its
subclasses to query and manipulate LDAP data.

Overview
--------

:py:class:`~ldaporm.managers.LdapManager` provides a Django QuerySet-like
interface for LDAP operations.  It handles LDAP searches, filtering, and CRUD
operations while maintaining a familiar Django API.

All automatically have their ``objects`` attribute set to an instance of
:py:class:`~ldaporm.managers.LdapManager`, but you can override this by
setting the ``objects`` attribute to an instance of a subclass of
:py:class:`~ldaporm.managers.LdapManager`.

What's New (2025)
-----------------

- **Direct Iteration:** You can now iterate over query results directly, without needing to call ``.all()``.
- **Slicing and Indexing:** Query results support Python slicing and indexing. Slicing with ``[:stop]`` is efficient; other slices fetch all results then slice in Python.
- **Convenience Methods:** ``.count()``, ``.as_list()``, ``.get_or_none()``, and ``.first_or_none()`` are available on both F and LdapManager objects.
- **Backward Compatibility:** ``.all()`` is still supported and works as before.

Examples:

.. code-block:: python

   # Direct iteration (no .all() needed)
   for user in User.objects.filter(is_active=True):
       print(user.uid)

   # Indexing
   first_user = User.objects.filter(is_active=True)[0]

   # Efficient slicing (fetches only first 10 results)
   first_ten = User.objects.filter(is_active=True)[:10]

   # Inefficient slicing (fetches all, then slices)
   middle_five = User.objects.filter(is_active=True)[5:10]

   # Count
   num_active = User.objects.filter(is_active=True).count()

   # as_list
   user_list = User.objects.filter(is_active=True).as_list()

   # get_or_none
   user = User.objects.get_or_none(uid='john.doe')

   # first_or_none
   user = User.objects.filter(is_active=True).first_or_none()

.. note::
   You can still use ``.all()`` for backward compatibility:

   .. code-block:: python

      users = User.objects.filter(is_active=True).all()


Subclassing
^^^^^^^^^^^

You can subclass :py:class:`~ldaporm.managers.LdapManager` to add custom
methods to your manager.  For example you can add new methods to your manager
to do common operations on your LDAP objects.

.. code-block:: python

   from datetime import datetime
   from zoneinfo import ZoneInfo
   from typing import Any

   from ldaporm.managers import LdapManager

   class MyManager(LdapManager):

       def reset_password(
           self,
           uid: str,
           new_password: str,
           attributes: dict[str, Any] | None = None,
       ) -> bool:
           """
           Reset a user's password and also set our "CustomLastPasswordChange"
           attribute to the current time in ISO format.

           Args:
               uid: The uid of the user to reset the password for.
               new_password: The new password to set.
               attributes: Additional attributes to set on the user.

           Returns:
               True if the password was reset, False otherwise.
           """
           if not attributes:
               attributes = {}

           attributes['CustomLastPasswordChange'] = datetime.now(tz=ZoneInfo('UTC')).isoformat()
           return super().reset_password(uid, new_password, attributes)

   class MyModel(Model):
       objects = MyManager()


Basic Usage
-----------

Querying Objects
^^^^^^^^^^^^^^^^

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import CharField

   class User(Model):
       uid = CharField('uid', primary_key=True, max_length=50)
       cn = CharField('cn', max_length=100)
       mail = CharField('mail', max_length=254)

       class Meta:
           ldap_server = 'default'
           basedn = 'ou=users,dc=example,dc=com'
           objectclass = 'person'

   # Get all users (you can iterate over them directly)
   for user in User.objects:
       print(user.uid)

   # Or get as a list
   users = list(User.objects)

   # Get a specific user
   user = User.objects.get(uid='john.doe')

   # Get a user by its full DN
   user = User.objects.get_by_dn('uid=john.doe,ou=users,dc=example,dc=com')

   # Use a filter to get a specific user.  If more than one user matches, you'll
   # get a :py:class:`~ldaporm.exceptions.MultipleObjectsReturned` error.
   # If the user doesn't exist, you'll get a :py:class:`~ldaporm.exceptions.DoesNotExist` error.
   user = User.objects.get(uid__istartswith='john')

   # Get a user or None if they don't exist.  You'll get a
   # :py:class:`~ldaporm.exceptions.MultipleObjectsReturned` error if more than
   # one user matches the filter.
   user = User.objects.get_or_none(uid='john.doe')

   # Get first user
   first_user = User.objects.first_or_none()

   # Get last user
   last_user = User.objects.as_list()[-1]

   # Just tell me if a user exists
   if User.objects.filter(uid='john.doe').exists():
       print("User exists")
   else:
       print("User does not exist")

.. note::
   You no longer need to append ``.all()`` to execute queries, but it is still
   supported for backward compatibility.

Filtering
---------

If you have ``paged_search`` in your ``Meta.options`` list for your model,
all filtering is done with paged, asynchronous searches.  This means that
you can filter for a large number of objects and not worry about running
into server side limits or timeouts.

Otherwise, all filtering is done with synchronous searches.  This means that
you will get all the results at once.

.. important::

    Again LDAP is weird and is not SQL.  These things from Django's ORM are not
    supported:

    * ``exclude()``
    * ``distinct()``

.. important::

    You can now iterate, index, and slice query results directly. ``.all()`` is no longer required to execute queries.

Basic Filtering
^^^^^^^^^^^^^^^

Use Django-style filtering:

.. code-block:: python

   # Filter by exact match
   active_users = User.objects.filter(is_active=True)
   john_users = User.objects.filter(cn='John Doe')

   # Filter by multiple conditions
   active_johns = User.objects.filter(
       is_active=True,
       cn__icontains='John'
   )

   # Use wildcards
   users = User.objects.wildcard(cn='*john*')

Field Lookups
^^^^^^^^^^^^^

LDAP supports case-insensitive string comparisons and integer comparisons.  String
lookups are case-insensitive, while integer comparisons are only available for
:py:class:`~ldaporm.fields.IntegerField` and its subclasses.

.. code-block:: python

   # String lookups
   users = User.objects.filter(cn__exists='john')
   users = User.objects.filter(cn__icontains='john')
   users = User.objects.filter(cn__istartswith='John')
   users = User.objects.filter(cn__iendswith='Doe')
   users = User.objects.filter(givenName__iexact='John')
   users = User.objects.filter(givenName='John')

   # List lookups
   users = User.objects.filter(cn__in=['John Doe', 'Jane Smith'])

   # Integer comparisons (only for IntegerField and subclasses)
   users = User.objects.filter(uidNumber__gt=1000)
   users = User.objects.filter(uidNumber__gte=1000)
   users = User.objects.filter(uidNumber__lt=10000)
   users = User.objects.filter(uidNumber__lte=10000)

.. important::

    Integer comparison operators (``__gt``, ``__gte``, ``__lt``, ``__lte``) can only
    be used on :py:class:`~ldaporm.fields.IntegerField` or its subclasses. Using these
    operators on other field types will raise a :py:exc:`TypeError`.


Complex Queries
^^^^^^^^^^^^^^^

You can chain your filters together just like you would with a Django QuerySet:

.. code-block:: python

   #Filter on multiple fields in one filter()
   users = User.objects.filter(
       cn__icontains='john',
       is_active=True,
       cn__icontains='admin'
   )

   # Use chaining instead
   users = User.objects.filter(
       cn__icontains='john'
   ).filter(
       is_active=True
   ).filter(
       cn__icontains='admin'
   )

You can also use :py:class:`ldaporm.managers.F` objects to build more complex
queries, similarly to Django's :py:class:`~django.db.models.Q` objects:

.. code-block:: python

   # AND operation
   users = User.objects.filter(
       F(cn__icontains='john') & F(is_active=True)
   )

   # OR operation
   users = User.objects.filter(
       F(cn__icontains='john') | F(cn__icontains='admin')
   )

   # Complex combinations - use parentheses to control precedence
   users = User.objects.filter(
       (F(cn__icontains='john') & F(is_active=True)) | F(cn__icontains='admin')
   )

.. note::

   When using :py:class:`ldaporm.managers.F`, you can construct F() without
   passing a manager. If you use ``F()`` as an argument to a manager's
   :py:meth:`~ldaporm.managers.LdapManager.filter` method (e.g.
   ``User.objects.filter(F(...))``), the manager will automatically bind itself
   to the F instance. If you use ``F()`` outside of a manager context, you must
   bind it manually or use ``F(manager, ...)``.

Finally, if you just can't do it any other way, you can do a raw LDAP search,
via the ``.search()`` method directly:

.. code-block:: python

   users = User.objects.search(
       '(cn=*admin*)',
       attrlist=['uid', 'cn', 'mail']
       size_limit=1000,
   )


Debugging the actual LDAP query
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can debug the actual LDAP query that will by printing the
the ``__str__`` method on the :py:class:`~ldaporm.managers.F` object::

.. code-block:: python

   # This will print the actual LDAP query that will be sent to the server
   >>> print(User.objects.filter(cn__icontains='john'))
   (cn=*john*)


Ordering
--------

``django-ldaporm`` supports server-side sorting using the LDAP Control Extension
for Server-Side Sorting (RFC 2891, OID 1.2.840.113556.1.4.473). This control is
supported by 389 Directory Server and Active Directory by default.  OpenLDAP
supports this control, but it is not enabled by default; you must enable it in
your server's configuration.

.. info::
    To enable server-side sorting in OpenLDAP, you must add the following to
    your ``slapd.conf`` file (old style):

    .. code-block:: text

        overlay sssvlv

    Or the following to your ``cn=config`` entry (new style):

        dn: olcOverlay=sssvlv,olcDatabase={1}mdb,cn=config
        objectClass: olcOverlayConfig
        objectClass: olcSssVlvConfig
        olcOverlay: sssvlv


When you use :py:meth:`~ldaporm.managers.F.order_by`, the library will:

1. **Check server capabilities**: Query the LDAP server's Root DSE to determine if it supports
   server-side sorting via the ``supportedControl`` attribute.

2. **Server-side sorting**: If the server supports the sorting control, the sorting is performed
   on the server side, which is much more efficient for large result sets.

3. **Client-side fallback**: If the server doesn't support server-side sorting, the library
   automatically falls back to client-side sorting with a warning message.

.. important::

    Server-side sorting is only available when the LDAP server supports the Server-Side Sorting
    control (OID 1.2.840.113556.1.4.473). If your server doesn't support this control, sorting
    will be performed on the client side, which can be inefficient for large result sets.

    The capability check is cached per server configuration, so subsequent queries to the same
    server won't need to re-check the server's capabilities.

.. note::

    Connection errors (``ldap.SERVER_DOWN``, ``ldap.CONNECT_ERROR``) during capability checking
    will propagate up the stack rather than falling back to client-side sorting, as these errors
    make the test inconclusive.

Here's how you sort query results:

.. code-block:: python

   # Single field ordering
   users = User.objects.order_by('cn')
   users = User.objects.order_by('-cn')  # Descending

   # Multiple field ordering
   users = User.objects.order_by('department', 'cn')

   # The sorting will be performed server-side if supported, otherwise client-side
   # You'll see a warning message if falling back to client-side sorting:
   # "LDAP server does not support server-side sorting (OID: 1.2.840.113556.1.4.473).
   # Falling back to client-side sorting."

Limiting Results
----------------

.. important::

    Slicing with ``[:stop]`` (e.g., ``[:10]``) is efficient and only fetches up
    to ``stop`` results from the server. Other slices (e.g., ``[5:15]``,
    ``[::-1]``) fetch all results and then slice in Python.

    You can now use Python slicing and indexing directly on query results.
    ``.all()`` is no longer required.

.. code-block:: python

   # Efficient: fetches only first 10 results
   users = User.objects.filter(is_active=True)[:10]

   # Inefficient: fetches all, then slices
   users = User.objects.filter(is_active=True)[5:15]

   # Indexing
   user = User.objects.filter(is_active=True)[0]

   # Backward compatible
   users = User.objects.filter(is_active=True).all()

   # Count
   num_users = User.objects.count()

   # as_list
   user_list = User.objects.as_list()

   # get_or_none
   user = User.objects.get_or_none(uid='john.doe')

   # first_or_none
   user = User.objects.filter(is_active=True).first_or_none()

Limiting the attributes returned
--------------------------------

You can limit the attributes returned by your query by using the ``.only()``
parameter.  This is useful if you only need a few attributes from the LDAP
object and don't want to pull in the entire object.

.. code-block:: python

   # Only return the uid and cn attributes
   >>> User.objects.only('uid', 'cn')
   [<User: uid=johndoe, cn=John Doe>, <User: uid=janedoe, cn=Jane Doe>]

   # Only return the uid attribute
   >>> User.objects.filter(uid='johndoe').only('uid')
   [<User: uid=johndoe>]


Getting values instead of objects
---------------------------------

.. important::

    ``.values()`` and ``.values_list()`` cannot be used with ``.only()``.
    You'll get a :py:class:`NotImplementedError` if you try.

You can get values instead of objects by using the ``.values()`` or
``.values_list()`` methods.   You don't need to append ``.all()`` to these
methods.

.. code-block:: python

   # Get a list of dictionaries with the uid and cn attributes
   >>> User.objects.values('uid', 'cn')
   [{'uid': 'johndoe', 'cn': 'John Doe'}, {'uid': 'janedoe', 'cn': 'Jane Doe'}]

   # Get a list of tuples with the uid and cn attributes
   >>> User.objects.values_list('uid', 'cn')
   [('johndoe', 'John Doe'), ('janedoe', 'Jane Doe')]

   # If you only want a single value and have that be returned as a list of
   # values, you can use the ``.values_list(attr, flat=True)`` method:
   >>> User.objects.values_list('uid', flat=True)
   ['johndoe', 'janedoe']


Object Lifecycle
----------------

Create new LDAP objects
^^^^^^^^^^^^^^^^^^^^^^^

For almost all purposes, you'll want to use the ``.save()`` method to create an
object.  If you really want to update using the manager, you can use the
``.add()`` or ``.create()`` methods.

.. code-block:: python

   # Method 1: Create and save
   user = User(
       uid='john.doe',
       cn='John Doe',
       mail='john.doe@example.com'
   )
   user.save()

   # Method 2: Create with manager
   user = User(
       uid='jane.smith',
       cn='Jane Smith',
       mail='jane.smith@example.com'
   )
   User.objects.add(user)

   # Create with attributes
   user = User.objects.create(
       uid='jane.smith',
       cn='Jane Smith',
       mail='jane.smith@example.com'
   )


Modifying Existing Objects
^^^^^^^^^^^^^^^^^^^^^^^^^^

For almost all purposes, you'll want to use the ``.save()`` method to update an
object.  If you really want to update using the manager, you can use the
``.modify()`` method.

.. code-block:: python

   # Method 1: Update individual object
   user = User.objects.get(uid='john.doe')
   user.cn = 'John Smith'
   user.mail = 'john.smith@example.com'
   user.save()

   # Method 2: Update with manager
   from copy import deepcopy

   user = User.objects.get(uid='john.doe')
   new_user = deepcopy(user)
   new_user.cn = 'John Smith'
   new_user.mail = 'john.smith@example.com'
   User.objects.modify(user, new_user)


Deleting Objects
^^^^^^^^^^^^^^^^

Delete LDAP objects:

.. code-block:: python

   # Method 1: Delete individual object
   user = User.objects.get(uid='john.doe')
   user.delete()

   # Method 2: Delete with a manager filter.  This will only delete a single object,
   # so if uid__istartswith='john' matches multiple objects, you'll get a
   # :py:class:`~ldaporm.exceptions.MultipleObjectsReturned` error.
   User.objects.delete(uid__istartswith="john")

   # Method 3: Delete an object you already have
   User.objects.delete_obj(user)

DN management
-------------

DN (Distinguished Name) management means getting or changing the DN of an
object.

.. code-block:: python

   # Get the DN of an object
   >>> User.objects.get(uid='john.doe').dn
   'uid=john.doe,ou=users,dc=example,dc=com'

   # Get the DN of an object by its primary key.  This does not require a
   # database lookup, so it's much faster.  It uses the basedn from the model's
   # Meta class, and the primary key attribute from the model.
   >>> User.objects.get_dn('john.doe')
   'uid=john.doe,ou=users,dc=example,dc=com'

   # Get the DN of an object by its primary key
   >>> User.objects.get_dn('john.doe')
   'uid=john.doe,ou=users,dc=example,dc=com'

   # Rename an object
   User.objects.rename(
        old_dn='uid=john.doe,ou=users,dc=example,dc=com',
        new_dn='uid=john.smith,ou=users,dc=example,dc=com'
    )

Authentication and Password Management
--------------------------------------

You can authenticate and reset passwords using the ``.authenticate()`` and
``.reset_password()`` methods.

.. important::

    Passwords will be hashed using the SHA1 algorithm.

.. code-block:: python

   # Authenticate a user
   >>> User.objects.authenticate('john.doe', 'password')
   True

   # Reset a user's password
   >>> User.objects.reset_password('john.doe', 'newpassword')
   True


   # Reset a user's password with additional attributes
   >>> User.objects.reset_password('john.doe', 'newpassword', {'mail': 'john.doe@example.com'})
   True


Connection Management
---------------------

It's going to be rare that you need to do this, but if you do, here's how you
managed the direct ``python-ldap`` connections.

.. code-block:: python

   # Get the actual LDAP connection object
   >>> User.objects.connection
   <ldap.ldapobject.LDAPObject object at 0x7f0000000000>

   # Connect directly with a dn and password, where ``default`` is the name of
   # the LDAP configuration in your ``settings.LDAP_SERVERS`` dictionary.
   >>> User.objects.connect('default', 'cn=admin,dc=example,dc=com', 'password')

   # Disconnect the current thread's LDAP connection
   >>> User.objects.disconnect()

   # Check if the current thread has an active LDAP connection
   >>> User.objects.has_connection()
   True

   # Set the LDAP connection object for the current thread
   >>> import ldap
   >>> ldap_obj = ldap.initialize('ldap://localhost:389')
   >>> ldap_obj.set_option(ldap.OPT_REFERRALS, 0)
   >>> ldap_obj.set_option(ldap.OPT_NETWORK_TIMEOUT, 15.0)
   >>> ldap_obj.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
   >>> ldap_obj.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
   >>> ldap_obj.start_tls_s()
   >>> ldap_obj.simple_bind_s('cn=admin,dc=example,dc=com', 'password')
   >>> User.objects.set_connection(ldap_obj)

   # Just get the a new connection object.  ``default`` is the name of the LDAP
   # configuration in your ``settings.LDAP_SERVERS`` dictionary.
   >>> User.objects.new_connection('default')
   <ldap.ldapobject.LDAPObject object at 0x7f0000000000>



Performance Optimization
------------------------

Indexing
^^^^^^^^

Use LDAP indexes for better performance.  This of course needs to be configured
on the server side.

Caching
^^^^^^^

Implement caching for frequently accessed data:

.. code-block:: python

   from django.core.cache import cache

   def get_user_by_uid(uid):
       cache_key = f'user_{uid}'
       user = cache.get(cache_key)

       if user is None:
           user = User.objects.get(uid=uid)
           cache.set(cache_key, user, 300)  # Cache for 5 minutes

       return user

Selective Field Loading
^^^^^^^^^^^^^^^^^^^^^^

Load only needed fields:

.. code-block:: python

   # Load only specific fields
   users = User.objects.values('uid', 'cn')  # Only uid and cn
   users = User.objects.values_list('uid', flat=True)  # Only uid as list

Error Handling
--------------

Handle LDAP errors gracefully:

.. code-block:: python

   from ldaporm.exceptions import LDAPError

   try:
       user = User.objects.get(uid='nonexistent')
   except User.DoesNotExist:
       print("User not found")
   except LDAPError as e:
       print(f"LDAP error: {e}")

   # Check if object exists
   if User.objects.filter(uid='john.doe').exists():
       user = User.objects.get(uid='john.doe')


Example: Complete User Management
---------------------------------

Here's a complete example of user management operations:

.. code-block:: python

   import ldap
   from ldaporm import Model
   from ldaporm.fields import CharField, EmailField, BooleanField, CharListField
   from ldaporm.managers import F
   from django.utils import timezone

   class User(Model):
       uid = CharField('uid', primary_key=True, max_length=50)
       cn = CharField('cn', max_length=100)
       sn = CharField('sn', max_length=100)
       givenName = CharField('givenName', max_length=100)
       mail = EmailField('mail', max_length=254)
       is_active = BooleanField('userAccountControl', default=True)
       memberOf = CharListField('memberOf', max_length=100)

       class Meta:
           ldap_server = 'default'
           basedn = 'ou=users,dc=example,dc=com'
           objectclass = 'person'

   class Group(Model):
       cn = CharField('cn', primary_key=True, max_length=50)
       description = CharField('description', max_length=200, blank=True)
       member = CharListField('member', max_length=100)

       class Meta:
           ldap_server = 'default'
           basedn = 'ou=groups,dc=example,dc=com'
           objectclass = 'groupOfNames'

   # User management functions
   def create_user(
       uid: str,
       first_name: str,
       last_name: str,
       email: str,
       groups: list[str] | None = None,
   ) -> User | None:
       """
       Create a new user with group memberships.

       Args:
           uid: The uid of the user to create.
           first_name: The first name of the user.
           last_name: The last name of the user.
           email: The email of the user.
           groups: The cns of the groups to add the user to.

       Raises:
           ldap.LDAPError: The LDAP server returned an error we don't know how
                to handle.

       Returns:
           The created user.
       """
        # Create user
        user = User.objects.create(
            uid=uid,
            cn=f"{first_name} {last_name}",
            givenName=first_name,
            sn=last_name,
            mail=email,
            is_active=True
        )

        # Add to groups
        if groups:
            for group_name in groups:
                try:
                    group = Group.objects.get(cn=group_name)
                    group.member.append(user.dn)
                    group.save()
                    user.memberOf.append(group.dn)
                except Group.DoesNotExist:
                    print(f"Group {group_name} not found")

        user.save()
        return user

       except Exception as e:
           print(f"Failed to create user: {e}")
           return None

   def deactivate_user(uid: str) -> bool:
       """
       Deactivate a user and remove from all groups.

       Args:
           uid: The uid of the user to deactivate.

       Raises:
            ldap.LDAPError: The LDAP server returned an error we don't know how
                to handle.

       Returns:
           True if the user was deactivated, False otherwise.
       """

        try:
            user = User.objects.get(uid=uid)
       except User.DoesNotExist:
           print(f"User {uid} not found")
           return False

        # Remove from all groups
        for group_dn in user.memberOf:
            try:
                group = Group.objects.get(dn=group_dn)
                if user.dn in group.member:
                    group.member.remove(user.dn)
                    group.save()
            except Group.DoesNotExist:
                pass
        user.is_active = False
        user.memberOf = []
        user.save()
        return True

   def search_users(query: str, department: str | None = None, active_only: bool = True) -> list[User]:
       """
       Search users with various criteria.

       Args:
           query: The query to search for.
           department: The department to search for.
           active_only: Whether to only return active users.

       Returns:
           A list of users that match the query.
       """
       filters = F(cn__icontains=query) | F(mail__icontains=query)

       if department:
           filters &= F(department=department)

       if active_only:
           filters &= F(is_active=True)

       return User.objects.filter(filters).order_by('cn')

   def get_user_stats() -> dict[str, int | list[dict[str, int]]]:
       """
       Get user statistics.

       Returns:
           A dictionary with the following keys:
           - total: The total number of users.
           - active: The number of active users.
           - inactive: The number of inactive users.
       """
       total_users = len(User.objects.all())
       active_users = len(User.objects.filter(is_active=True))
       inactive_users = total_users - active_users

       return {
           'total': total_users,
           'active': active_users,
           'inactive': inactive_users,
       }

   # Usage examples
   if __name__ == '__main__':
       # Create a new user
       user = create_user(
           uid='john.doe',
           first_name='John',
           last_name='Doe',
           email='john.doe@example.com',
           groups=['users', 'developers']
       )

       # Search for users
       developers = search_users('developer', department='Engineering')

       # Get statistics
       stats = get_user_stats()
       print(f"Total users: {stats['total']}")
       print(f"Active users: {stats['active']}")

       # Deactivate a user
       deactivate_user('john.doe')