Model Construction and Implementation
=====================================

This document describes how LDAP ORM models are constructed from their field
definitions and Meta classes, and how this process compares to Django's own
model construction.

Overview
--------

The LDAP ORM uses a metaclass-based approach to construct models, similar to
Django's ORM. When you define a model class, the metaclass processes the class
attributes and ``Meta`` class to create a fully functional model with all necessary
metadata, field mappings, and manager setup.

The construction process involves several key components:

* :py:class:`~ldaporm.models.LdapModelBase` - The metaclass that orchestrates model creation
* :py:class:`~ldaporm.options.Options` - The metadata container (similar to Django's Model._meta)
* :py:class:`~ldaporm.fields.Field` - Field instances that define model attributes
* :py:class:`~ldaporm.managers.LdapManager` - The default manager for model operations

Model Construction Process
--------------------------

When you define a model class, the following sequence occurs:

1. **Class Definition Detection**: The metaclass checks if the class inherits from :py:class:`~ldaporm.models.Model`
2. **Basic Class Creation**: A basic class object is created with minimal attributes
3. **Meta Class Processing**: The Meta class is extracted and processed into an Options instance
4. **Field Registration**: Each field attribute is registered with the model
5. **Model Preparation**: Final setup including manager creation and validation
6. **Signal Emission**: The class_prepared signal is sent

Here's a detailed breakdown of each step:

### 1. Class Definition Detection

The metaclass first checks if the class being created inherits from a model class:

.. code-block:: python

    def __new__(cls, name, bases, attrs, **kwargs):
        super_new = super().__new__
        parents = [b for b in bases if isinstance(b, LdapModelBase)]
        if not parents:
            return super_new(cls, name, bases, attrs)

        # Process as a model class...

This ensures that only classes inheriting from :py:class:`~ldaporm.models.Model` are processed as models.

### 2. Basic Class Creation

A basic class object is created with essential attributes:

.. code-block:: python

    module = attrs.pop("__module__")
    new_attrs = {"__module__": module}
    classcell = attrs.pop("__classcell__", None)
    if classcell is not None:
        new_attrs["__classcell__"] = classcell
    new_class = super_new(cls, name, bases, new_attrs, **kwargs)

### 3. Meta Class Processing

The Meta class is extracted and converted to an Options instance:

.. code-block:: python

    attr_meta = attrs.pop("Meta", None)
    meta = attr_meta or getattr(new_class, "Meta", None)
    new_class.add_to_class("_meta", Options(meta))

The :py:class:`~ldaporm.options.Options` class processes the Meta class
attributes and sets up default values for LDAP-specific configuration.

If a model is a subclass of another model, the Meta classes are combined in
MRO (Method Resolution Order). This means that the Meta class for the subclass
will have all the options from the parent class, plus any options that are
defined or overridden in the subclass. This allows for inheritance of LDAP
configuration while still allowing subclasses to customize specific options.

### 4. Field Registration

Each field attribute is registered with the model:

.. code-block:: python

    for obj_name, obj in attrs.items():
        new_class.add_to_class(obj_name, obj)

The :py:meth:`add_to_class` method calls :py:meth:`contribute_to_class` on field
objects, which registers them with the model's metadata.

### 5. Model Preparation

Final setup occurs in the :py:meth:`_prepare` method:

.. code-block:: python

    def _prepare(cls) -> None:
        opts = cls._meta
        opts._prepare(cls)

        # Add manager
        manager = opts.manager_class()
        cls.add_to_class("objects", manager)

        # Send signal
        class_prepared.send(sender=cls)

### 6. Signal Emission

The :py:data:`~django.db.models.signals.class_prepared` signal is sent to notify
other parts of the system that the model class is ready.

Field Registration Process
--------------------------

When a field is added to a model, the following occurs:

1. **Field Validation**: The field's :py:meth:`check` method validates its configuration
2. **Metadata Registration**: The field is added to the model's field list
3. **Primary Key Setup**: If the field is marked as primary_key, it's set as the model's pk
4. **Attribute Mapping**: Field names are mapped to LDAP attribute names

Example field registration:

.. code-block:: python

    class LDAPUser(Model):
        uid = CharField('uid', primary_key=True, max_length=50)
        cn = CharField('cn', max_length=100)

When this model is created:

* The `uid` field is registered and marked as the primary key
* The `cn` field is registered as a regular field
* Both fields are added to the model's field list
* LDAP attribute mappings are created (uid → uid, cn → cn)

Meta Class Processing
---------------------

The Meta class is processed by the :py:class:`~ldaporm.options.Options` class, which:

1. **Sets Default Values**: Establishes default values for all configurable options
2. **Processes Meta Attributes**: Extracts and validates Meta class attributes
3. **Creates Mappings**: Builds field-to-attribute and attribute-to-field mappings
4. **Validates Configuration**: Ensures required options are present

Example Meta processing:

.. code-block:: python

    class Meta:
        ldap_server = 'default'
        basedn = 'ou=users,dc=example,dc=com'
        objectclass = 'person'

This Meta class would result in:

* LDAP server configuration from settings.LDAP_SERVERS['default']
* Base DN for searches set to 'ou=users,dc=example,dc=com'
* Object class filtering for 'person' objects
* Automatic addition of an objectclass field to the model

Comparison with Django's Model Construction
-------------------------------------------

The LDAP ORM model construction process closely mirrors Django's approach, with
some key differences:

### Similarities

* **Metaclass-based**: Both use metaclasses to process class definitions
* **Field Registration**: Both register fields through contribute_to_class
* **Meta Processing**: Both process Meta classes into metadata objects
* **Manager Setup**: Both create default managers
* **Signal System**: Both emit class_prepared signals

### Key Differences

* **LDAP-Specific Options**: LDAP ORM adds LDAP-specific configuration options
* **Attribute Mapping**: LDAP ORM maps Python field names to LDAP attribute names
* **Object Class Handling**: LDAP ORM automatically adds objectclass fields
* **Primary Key Requirements**: LDAP ORM requires explicit primary key fields
* **No Database Migration**: LDAP ORM doesn't generate database migrations

### Django's ModelBase vs LdapModelBase

Django's ModelBase metaclass:

* Processes database-specific options (db_table, indexes, etc.)
* Handles model inheritance and proxy models
* Sets up database connections and migrations
* Manages model relationships (ForeignKey, ManyToMany, etc.)

LDAP ORM's LdapModelBase metaclass:

* Processes LDAP-specific options (basedn, objectclass, etc.)
* Handles LDAP attribute mapping
* Sets up LDAP connections and search filters
* Manages LDAP-specific field types

Field Contribution Process
--------------------------

When a field is added to a model, it goes through the following process:

1. **Field Initialization**: The field's __init__ method sets up basic attributes
2. **Model Association**: The field is associated with its model class
3. **Validation**: The field's check method validates its configuration
4. **Registration**: The field is added to the model's field list
5. **Primary Key Setup**: If applicable, the field is set as the primary key

Example field contribution:

.. code-block:: python

    def contribute_to_class(self, cls, name: str) -> None:
        self.set_attributes_from_name(name)
        self.model = cls
        self.check()
        cls._meta.add_field(self)
        if self.choices:
            setattr(cls, f"get_{self.name}_display",
                   partialmethod(cls._get_FIELD_display, field=self))

This process ensures that:

* Field names are properly set
* Fields are associated with their model
* Field configuration is valid
* Fields are registered in the model's metadata
* Choice fields get display methods

Manager Setup
-------------

After all fields are registered, the model's manager is set up:

1. **Manager Creation**: An instance of the manager class is created
2. **Model Association**: The manager is associated with the model
3. **Configuration**: The manager is configured with model metadata
4. **Attribute Assignment**: The manager is assigned to the 'objects' attribute

The manager setup process:

.. code-block:: python

    def contribute_to_class(self, cls, accessor_name) -> None:
        self.pk = cls._meta.pk.name
        self.basedn = cls._meta.basedn
        self.objectclass = cls._meta.objectclass
        # ... other configuration
        self.model = cls
        cls._meta.base_manager = self
        setattr(cls, accessor_name, self)

This ensures that the manager has access to all necessary model metadata for
LDAP operations.

Conclusion
----------

The LDAP ORM model construction process provides a Django-like interface while
adapting to LDAP-specific requirements. The metaclass-based approach ensures
that models are properly configured with all necessary metadata, field mappings,
and manager setup before they're used.

This design allows developers familiar with Django to work with LDAP data using
familiar patterns, while the underlying implementation handles the complexities
of LDAP attribute mapping and object class management.
