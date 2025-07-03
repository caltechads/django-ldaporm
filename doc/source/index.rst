==============
django-ldaporm
==============

.. toctree::
   :caption: Overview
   :hidden:

   overview/quickstart
   overview/installation
   overview/configuration
   overview/models
   overview/fields
   overview/managers
   overview/implementation

.. toctree::
   :caption: Users Guide
   :hidden:

   overview/forms
   overview/views
   overview/admin
   overview/authentication
   overview/best_practices

.. toctree::
   :caption: Reference
   :hidden:

   api/models
   api/fields
   api/managers
   api/options
   api/forms

.. toctree::
   :caption: Runbook
   :hidden:

   runbook/development
   runbook/testing
   runbook/deployment

``django-ldaporm`` is a Django ORM-like module that allows you to treat LDAP
object classes like RDBMS tables. This enables you to use Django forms, fields,
and views natively with LDAP models, providing a familiar Django interface for
LDAP data management.

Overview
--------

``django-ldaporm`` provides three main components:

Models
   Django-like model classes that represent LDAP object classes, with field
   definitions that map to LDAP attributes. Models support validation, forms,
   and admin integration just like Django ORM models.

Fields
   Field types that handle conversion between Python data types and LDAP
   attribute formats, including support for Active Directory timestamps,
   binary data, and multi-valued attributes.

Managers
   Query managers that provide Django QuerySet-like interfaces for LDAP
   searches, including filtering, ordering, and CRUD operations.

Why django-ldaporm?
-------------------

Traditional LDAP programming requires working with low-level LDAP APIs, complex
filter strings, and manual data conversion. This approach is error-prone and
time-consuming, especially when building web applications that need to present
LDAP data through forms and views.

``django-ldaporm`` solves these problems by:

* **Familiar Interface**: Uses Django's well-known ORM patterns, making LDAP
  programming accessible to Django developers
* **Type Safety**: Provides proper type hints and validation for LDAP data
* **Form Integration**: Works seamlessly with Django forms and admin
* **Query Interface**: Offers Django QuerySet-like filtering and querying
* **Active Directory Support**: Includes specialized fields for Active Directory
  timestamps and other AD-specific features

Use Cases
---------

``django-ldaporm`` is particularly useful for:

* **User Management Systems**: Building web interfaces for managing LDAP users,
  groups, and organizational units
* **Directory Services**: Creating administrative tools for LDAP directories
* **Authentication Systems**: Integrating LDAP authentication with Django
  applications
* **Data Migration**: Converting between LDAP and other data sources
* **Reporting Tools**: Building dashboards and reports for LDAP data

Key Features
------------

* **Django ORM Compatibility**: Models work with Django forms, admin, and views
* **Active Directory Support**: Specialized fields for AD timestamps and attributes
* **Type Safety**: Full type hints for Python 3.10+ compatibility
* **Flexible Configuration**: Support for multiple LDAP servers and connection types
* **Validation**: Built-in field validation and model-level validation
* **Query Interface**: Django QuerySet-like filtering and querying
* **CRUD Operations**: Create, read, update, and delete LDAP objects

Installation
-----------

``django-ldaporm`` is a pure Python package that can be installed via pip:

.. code-block:: bash

   pip install django-ldaporm

For development installation:

.. code-block:: bash

   git clone https://github.com/your-repo/django-ldaporm.git
   cd django-ldaporm
   pip install -e .

Quick Start
----------

See the :doc:`quickstart guide <overview/quickstart>` for a complete example
of setting up and using django-ldaporm in your Django project.

Important People
---------------

* `Chris Malek <https://directory.caltech.edu/personnel/cmalek>`_ -
  Primary maintainer and contact for this package.