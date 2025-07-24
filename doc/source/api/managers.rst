Managers API Reference
======================

Manager Classes
---------------

.. autoclass:: ldaporm.managers.LdapManager
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: ldaporm.managers.F
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: ldaporm.managers.Modlist
   :members:
   :undoc-members:
   :show-inheritance:

VLV Controls
------------

VLV is Virtual List View. It is a feature of LDAP that allows you to
efficiently paginate through large result sets. It is supported by
OpenLDAP and Active Directory, and by OpenLDAP if you enable the
``overlay vlv`` feature.

.. autoclass:: ldaporm.managers.VlvRequestControl
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: ldaporm.managers.VlvResponseControl
   :members:
   :undoc-members:
   :show-inheritance:

Pagination
----------

.. autoclass:: ldaporm.managers.LdapVlvPagination
   :members:
   :undoc-members:
   :show-inheritance:

Decorators
----------

.. autofunction:: ldaporm.managers.atomic

.. autofunction:: ldaporm.managers.substitute_pk

.. autofunction:: ldaporm.managers.needs_pk