Virtual List View (VLV) Guide
=============================

This guide covers using Virtual List View (VLV) functionality in django-ldaporm for
efficient slicing of large LDAP result sets.

Overview
--------

Virtual List View (VLV) is an LDAP control that allows efficient slicing of large
result sets by requesting specific ranges of results directly from the server,
rather than fetching all results and slicing them on the client side. This is
particularly useful for pagination and displaying large datasets efficiently.

VLV is supported by:

- **389 Directory Server** (native support)
- **OpenLDAP** (with ``overlay sssvlv`` installed)
- **Active Directory** (limited support)

How it works
------------

- **Automatic VLV Detection:** VLV support is automatically detected based on server capabilities
- **Transparent Slicing:** VLV is used automatically when slicing query results
- **Fallback Support:** Falls back to client-side slicing when VLV is not supported
- **Context ID Management:** Automatic management of VLV context IDs for efficient pagination
- **Django Pagination Integration:** `LdapVlvPagination` class for Django pagination
- **OpenLDAP Warnings:** Automatic warnings when OpenLDAP is detected without sssvlv overlay

Basic Usage
-----------

VLV is used transparently when you slice query results:

.. code-block:: python

   from ldaporm.models import Model
   from ldaporm.fields import CharField

   class User(Model):
       uid = CharField(primary_key=True)
       cn = CharField()

       class Meta:
           basedn = "ou=users,dc=example,dc=com"
           objectclass = "posixAccount"

   # VLV is used automatically for slicing
   users = User.objects.filter(is_active=True)[10:20]  # Gets users 10-19

   # First 10 users
   first_ten = User.objects.all()[:10]

   # Users 50-99
   middle_users = User.objects.all()[50:100]

Server Support Detection
------------------------

VLV support is automatically detected for each LDAP server:

.. code-block:: python

   from ldaporm.managers import LdapManager

   manager = LdapManager(User)

   # Check if VLV is supported
   if manager.supports_vlv():
       print("VLV is supported")
   else:
       print("VLV is not supported, will use client-side slicing")

OpenLDAP Configuration
----------------------

For OpenLDAP servers, VLV requires the sssvlv overlay to be installed and configured:

1. **Install the overlay:**

   .. code-block:: bash

      # On Ubuntu/Debian
      sudo apt-get install slapd-modules-sssvlv

      # On CentOS/RHEL
      sudo yum install openldap-servers-overlays

2. **Configure the overlay in slapd.conf or cn=config:**

   .. code-block:: text

      # In slapd.conf
      moduleload sssvlv.la
      overlay sssvlv
      sssvlv-max 50

   Or in cn=config:

   .. code-block:: text

      dn: cn=module,cn=config
      objectClass: olcModuleList
      cn: module
      olcModulePath: /usr/lib/openldap
      olcModuleLoad: sssvlv.la

      dn: olcOverlay=sssvlv,olcDatabase={2}hdb,cn=config
      objectClass: olcOverlayConfig
      olcOverlay: sssvlv
      sssvlv-max: 50

3. **Restart slapd:**

   .. code-block:: bash

      sudo systemctl restart slapd

When OpenLDAP is detected without VLV support, django-ldaporm will log a warning
suggesting to install the sssvlv overlay.

Django Pagination Integration
-----------------------------

Use ``LdapVlvPagination`` for Django pagination with VLV:

.. code-block:: python

   from django.core.paginator import Paginator
   from ldaporm.managers import LdapVlvPagination

   # Create paginator with VLV support
   paginator = LdapVlvPagination(
       object_list=User.objects.filter(is_active=True),
       per_page=20
   )

   # Get page
   page = paginator.get_page(1)

   # Access page data
   for user in page.object_list:
       print(user.uid)

   # Check pagination info
   print(f"Page {page.number} of {page.paginator.num_pages}")
   print(f"Showing {len(page.object_list)} of {page.paginator.count} users")

Advanced Usage
-------------

Context ID Management
^^^^^^^^^^^^^^^^^^^^^

VLV uses context IDs to maintain state between requests. This is handled automatically:

.. code-block:: python

   # First slice - no context ID needed
   users1 = User.objects.all()[0:10]

   # Second slice - context ID from first response is used automatically
   users2 = User.objects.all()[10:20]

   # Third slice - context ID from second response is used
   users3 = User.objects.all()[20:30]

Error Handling
^^^^^^^^^^^^^^

VLV operations automatically fall back to client-side slicing if:

- VLV is not supported by the server
- VLV operation fails
- Server returns an error

.. code-block:: python

   # This will use VLV if supported, otherwise client-side slicing
   try:
       users = User.objects.all()[100:200]
   except Exception as e:
       # Handle any remaining errors
       print(f"Error: {e}")

Custom VLV Controls
^^^^^^^^^^^^^^^^^^^

You can create custom VLV controls for advanced use cases:

.. code-block:: python

   from ldaporm.managers import VlvRequestControl, VlvResponseControl

   # Create VLV request control
   vlv_control = VlvRequestControl(
       before_count=5,      # Number of entries before target
       after_count=5,       # Number of entries after target
       offset=100,          # Target position
       count=10,            # Number of entries to return
       context_id=b"ctx123" # Optional context ID
   )

   # Encode for LDAP request
   encoded_control = vlv_control.encode()

   # Decode VLV response control
   response_control = VlvResponseControl.decode(response_data)
   print(f"Target position: {response_control.target_position}")
   print(f"Content count: {response_control.content_count}")

Performance Considerations
--------------------------

VLV vs Client-Side Slicing
^^^^^^^^^^^^^^^^^^^^^^^^^^^

- **VLV (Server-side):** Only fetches the requested slice from the server
- **Client-side:** Fetches all results, then slices in Python

For large datasets, VLV is significantly more efficient:

.. code-block:: python

   # Efficient - only fetches 10 entries from server
   users = User.objects.all()[:10]  # Uses VLV if supported

   # Inefficient - fetches all users, then slices
   all_users = User.objects.all()
   first_ten = all_users[:10]  # Client-side slicing

Best Practices
--------------

1. **Use slicing for pagination:** Always use slicing for pagination rather than
   fetching all results and slicing on the client side.

2. **Check server support:** Use `supports_vlv()` to check if VLV is available
   before implementing VLV-specific features.

3. **Handle fallbacks gracefully:** Always handle the case where VLV is not
   supported.

4. **Monitor performance:** Use Django's query logging to monitor LDAP query
   performance.

5. **Configure OpenLDAP properly:** Ensure the sssvlv overlay is installed and
   configured for OpenLDAP servers.

Example: User Management Interface
---------------------------------

Here's a complete example of using VLV for a user management interface:

.. code-block:: python

   from django.core.paginator import Paginator
   from django.shortcuts import render
   from ldaporm.managers import LdapVlvPagination

   def user_list(request):
       # Get page number from request
       page_number = request.GET.get('page', 1)

       # Create query with filtering
       users_query = User.objects.filter(is_active=True).order_by('uid')

       # Create paginator with VLV support
       paginator = LdapVlvPagination(
           object_list=users_query,
           per_page=20
       )

       # Get page
       page = paginator.get_page(page_number)

       return render(request, 'users/list.html', {
           'page': page,
           'users': page.object_list,
       })

   # Template: users/list.html
   """
   <h1>Users</h1>

   <table>
       <tr><th>UID</th><th>Name</th></tr>
       {% for user in users %}
       <tr>
           <td>{{ user.uid }}</td>
           <td>{{ user.cn }}</td>
       </tr>
       {% endfor %}
   </table>

   {% if page.has_previous %}
       <a href="?page={{ page.previous_page_number }}">Previous</a>
   {% endif %}

   <span>Page {{ page.number }} of {{ page.paginator.num_pages }}</span>

   {% if page.has_next %}
       <a href="?page={{ page.next_page_number }}">Next</a>
   {% endif %}
   """

Troubleshooting
---------------

Common Issues
^^^^^^^^^^^^

1. **VLV not working on OpenLDAP:**
   - Ensure sssvlv overlay is installed
   - Check overlay configuration
   - Restart slapd after configuration changes

2. **Performance issues:**
   - Check if VLV is being used (enable debug logging)
   - Verify server supports VLV
   - Monitor LDAP query performance

3. **Context ID errors:**
   - Context IDs are managed automatically
   - Ensure proper error handling for VLV failures

Debugging
^^^^^^^^^

Enable debug logging to see VLV operations:

.. code-block:: python

   import logging
   logging.getLogger('ldaporm').setLevel(logging.DEBUG)

This will show:

- VLV support detection
- VLV control creation
- Fallback to client-side slicing
- Context ID management

