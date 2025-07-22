Testing Guide
=============

This guide covers how to author and run tests for the django-ldaporm project, including both the core library tests and demo application tests.

Prerequisites
-------------

Before running tests, ensure you have:

1. **Virtual Environment**: Activate the project's virtual environment

   .. code-block:: bash

      source .venv/bin/activate

2. **Dependencies**: Install all required dependencies

   .. code-block:: bash

      uv sync --group demo dev

Test Structure
--------------

The project has two main test suites:

- **Core Library Tests** (`ldaporm/tests/`): Tests for the ldaporm library itself
- **Demo Tests** (`sandbox/demo/tests/`): Tests for the demo application

Core Library Tests
------------------

The core library tests are located in `ldaporm/tests/` and cover:

- Field implementations and validation
- Model functionality
- Manager operations
- REST framework integration
- Form handling
- LDAP connection management

Running Core Tests
^^^^^^^^^^^^^^^^^^

Run all core library tests:

.. code-block:: bash

   python -m pytest ldaporm/tests/

Run specific test modules:

.. code-block:: bash

   # Test fields
   python -m pytest ldaporm/tests/test_f_class.py

   # Test managers
   python -m pytest ldaporm/tests/test_ldap_manager.py

   # Test REST framework integration
   python -m pytest ldaporm/tests/test_restframework.py

   # Test forms
   python -m pytest ldaporm/tests/test_forms.py

   # Test models
   python -m pytest ldaporm/tests/test_models.py

Run specific test classes:

.. code-block:: bash

   # Test binary field functionality
   python -m pytest ldaporm/tests/test_restframework.py::LdapModelSerializerTestCase::test_binary_field_serialization

   # Test field validation
   python -m pytest ldaporm/tests/test_f_class.py::FieldTestCase

   # Test manager operations
   python -m pytest ldaporm/tests/test_ldap_manager.py::ManagerTestCase

Run tests with verbose output:

.. code-block:: bash

   python -m pytest ldaporm/tests/ -v

Run tests with coverage:

.. code-block:: bash

   python -m pytest ldaporm/tests/ --cov=ldaporm --cov-report=html

Demo Application Tests
----------------------

The demo application tests are located in `sandbox/demo/tests/` and cover:

- API endpoints
- Model integration
- Authentication
- Business logic
- End-to-end workflows

Running Demo Tests
^^^^^^^^^^^^^^^^^^

Run all demo tests:

.. code-block:: bash

   cd sandbox
   python manage.py test --settings=demo.settings_test

Run specific demo test modules:

.. code-block:: bash

   # Test API endpoints
   python manage.py test --settings=demo.settings_test demo.api.tests

   # Test core functionality
   python manage.py test --settings=demo.settings_test demo.core.tests

   # Test user management
   python manage.py test --settings=demo.settings_test demo.users.tests

Run specific test classes:

.. code-block:: bash

   python manage.py test --settings=demo.settings_test demo.api.tests.UserAPITestCase
   python manage.py test --settings=demo.settings_test demo.core.tests.UserModelTestCase

Run tests with verbose output:

.. code-block:: bash

   python manage.py test -v 2

Integration Tests
-----------------

Integration tests require a running LDAP server. The project provides Docker-based LDAP servers for testing.

Setting Up Test LDAP Server
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Start the test LDAP server:

.. code-block:: bash

   cd sandbox
   docker-compose up -d ldap

Wait for the LDAP server to be ready:

.. code-block:: bash

   docker-compose logs ldap

Running Integration Tests
^^^^^^^^^^^^^^^^^^^^^^^^^

Run integration tests with the LDAP server:

.. code-block:: bash

   # Core library integration tests
   python -m pytest ldaporm/tests/ -m "integration"

   # Demo integration tests
   cd sandbox
   python manage.py test --settings=demo.settings_docker

Test Configuration
------------------

Test settings are configured in several ways:

1. **Core Library Tests**: Use Django test settings configured in test files
2. **Demo Tests**: Use `demo/settings_docker.py` for Docker-based testing
3. **Integration Tests**: Use LDAP server configuration from Docker Compose

Writing Tests
-------------

Guidelines for writing tests in the ``django-ldaporm`` project:

Test Structure
^^^^^^^^^^^^^^

Follow this structure for new test files:

.. code-block:: python

   """
   Tests for [module name].

   This module tests [brief description of what is being tested].
   """

   import unittest
   from unittest.mock import Mock, patch

   from django.test import TestCase
   from ldaporm import fields, models


   class TestCaseName(TestCase):
       """Test cases for [specific functionality]."""

       def setUp(self):
           """Set up test data."""
           pass

       def test_specific_functionality(self):
           """Test [specific functionality description]."""
           # Arrange
           # Act
           # Assert
           pass

Field Tests
^^^^^^^^^^^

When testing fields, follow this pattern:

.. code-block:: python

   def test_field_validation(self):
       """Test field validation."""
       field = fields.CharField(max_length=50)

       # Test valid value
       value = field.to_python("test")
       self.assertEqual(value, "test")

       # Test invalid value
       with self.assertRaises(ValidationError):
           field.to_python(None)

Model Tests
^^^^^^^^^^^

When testing models, use mock LDAP connections:

.. code-block:: python

   @patch('ldaporm.models.get_ldap_connection')
   def test_model_save(self, mock_connection):
       """Test model save operation."""
       mock_conn = Mock()
       mock_connection.return_value = mock_conn

       user = TestUser(username='testuser', cn='Test User')
       user.save()

       mock_conn.add_s.assert_called_once()

REST Framework Tests
^^^^^^^^^^^^^^^^^^^^

When testing REST framework integration:

.. code-block:: python

   def test_serializer_binary_field(self):
       """Test binary field serialization."""
       class UserSerializer(LdapModelSerializer):
           class Meta:
               model = TestUser

       # Test serialization
       instance = Mock()
       instance._meta.fields = [Mock(name='photo', __class__=fields.BinaryField)]
       instance.photo = b'test_data'

       serializer = UserSerializer()
       result = serializer.to_representation(instance)

       import base64
       expected = base64.b64encode(b'test_data').decode('utf-8')
       self.assertEqual(result['photo'], expected)

Demo Application Tests
^^^^^^^^^^^^^^^^^^^^^^

When testing the demo application:

.. code-block:: python

   from django.test import TestCase
   from django.urls import reverse
   from rest_framework.test import APITestCase


   class UserAPITestCase(APITestCase):
       """Test user API endpoints."""

       def setUp(self):
           """Set up test data."""
           self.user_data = {
               'username': 'testuser',
               'cn': 'Test User',
               'mail': 'test@example.com'
           }

       def test_create_user(self):
           """Test user creation via API."""
           url = reverse('api:user-list')
           response = self.client.post(url, self.user_data)

           self.assertEqual(response.status_code, 201)
           self.assertEqual(response.data['username'], 'testuser')

Test Data Management
--------------------

Managing test data for LDAP-based tests:

Fixtures
^^^^^^^^

Create test fixtures for consistent test data:

.. code-block:: python

   # test_fixtures.py
   TEST_USER_DATA = {
       'username': 'testuser',
       'cn': 'Test User',
       'mail': 'test@example.com',
       'sn': 'User',
       'givenName': 'Test'
   }

   TEST_GROUP_DATA = {
       'cn': 'testgroup',
       'description': 'Test Group'
   }

Mock LDAP Data
^^^^^^^^^^^^^^

Use mocks for LDAP data in unit tests:

.. code-block:: python

   @patch('ldaporm.managers.get_ldap_connection')
   def test_manager_filter(self, mock_connection):
       """Test manager filtering."""
       mock_conn = Mock()
       mock_connection.return_value = mock_conn

       # Mock LDAP search results
       mock_conn.search_s.return_value = [
           ('cn=testuser,ou=users,dc=example,dc=com', {
               'cn': [b'testuser'],
               'mail': [b'test@example.com']
           })
       ]

       users = TestUser.objects.filter(cn='testuser')
       self.assertEqual(len(users), 1)

Test Database Setup
^^^^^^^^^^^^^^^^^^^

For integration tests, set up test LDAP data:

.. code-block:: python

   def setUp(self):
       """Set up test LDAP data."""
       # Add test user to LDAP
       user_dn = 'cn=testuser,ou=users,dc=example,dc=com'
       user_attrs = {
           'objectClass': [b'person', b'organizationalPerson', b'inetOrgPerson'],
           'cn': [b'testuser'],
           'sn': [b'User'],
           'mail': [b'test@example.com']
       }

       self.ldap_conn.add_s(user_dn, ldap.modlist.addModlist(user_attrs))

Continuous Integration
----------------------

The project uses GitHub Actions for continuous integration. Tests are automatically run on:

- Pull requests
- Pushes to main branch
- Scheduled runs

CI Configuration
^^^^^^^^^^^^^^^^

The CI pipeline:

1. Sets up Python environment
2. Installs dependencies
3. Starts LDAP server containers
4. Runs core library tests
5. Runs demo application tests
6. Generates coverage reports

Local CI Simulation
^^^^^^^^^^^^^^^^^^^

Simulate CI locally:

.. code-block:: bash

   # Run all tests as CI would
   make test

   # Run with Docker services
   python -m pytest ldaporm/tests/ --cov=ldaporm
   cd sandbox && python manage.py test --settings=demo.settings_test

Troubleshooting
---------------

Common test issues and solutions:

LDAP Connection Issues
^^^^^^^^^^^^^^^^^^^^^^

If tests fail with LDAP connection errors:

.. code-block:: bash

   # Check if LDAP server is running
   docker-compose ps

   # Restart LDAP server
   docker-compose restart ldap

   # Check LDAP server logs
   docker-compose logs ldap

Test Isolation Issues
^^^^^^^^^^^^^^^^^^^^^

If tests interfere with each other:

.. code-block:: python

   def tearDown(self):
       """Clean up after each test."""
       # Remove test data from LDAP
       try:
           self.ldap_conn.delete_s('cn=testuser,ou=users,dc=example,dc=com')
       except ldap.NO_SUCH_OBJECT:
           pass

Performance Issues
^^^^^^^^^^^^^^^^^^

For slow tests:

.. code-block:: bash

   # Run tests in parallel
   python -m pytest ldaporm/tests/ -n auto

   # Run only fast tests
   python -m pytest ldaporm/tests/ -m "not slow"

Best Practices
--------------

1. **Test Isolation**: Each test should be independent and not rely on other tests
2. **Mock External Dependencies**: Use mocks for LDAP connections in unit tests
3. **Use Descriptive Names**: Test method names should clearly describe what is being tested
4. **Arrange-Act-Assert**: Structure tests with clear setup, execution, and verification phases
5. **Test Edge Cases**: Include tests for error conditions and boundary values
6. **Use Fixtures**: Create reusable test data and configurations
7. **Documentation**: Include docstrings explaining what each test verifies

Example Test Suite
------------------

Here's a complete example of a test suite:

.. code-block:: python

   """
   Tests for User model functionality.

   This module tests user creation, validation, and LDAP operations.
   """

   import unittest
   from unittest.mock import Mock, patch

   from django.test import TestCase
   from django.core.exceptions import ValidationError

   from ldaporm import fields, models


   class TestUser(models.Model):
       """Test user model."""
       username = fields.CharField(max_length=50, primary_key=True)
       cn = fields.CharField(max_length=100)
       mail = fields.EmailField()
       photo = fields.BinaryField(blank=True, null=True)

       class Meta:
           basedn = "ou=users,dc=example,dc=com"
           objectclass = "person"
           ldap_server = "test_server"


   class UserModelTestCase(TestCase):
       """Test cases for User model."""

       def setUp(self):
           """Set up test data."""
           self.user_data = {
               'username': 'testuser',
               'cn': 'Test User',
               'mail': 'test@example.com'
           }

       def test_user_creation(self):
           """Test user creation with valid data."""
           user = TestUser(**self.user_data)
           self.assertEqual(user.username, 'testuser')
           self.assertEqual(user.cn, 'Test User')
           self.assertEqual(user.mail, 'test@example.com')

       def test_user_validation(self):
           """Test user validation."""
           # Test invalid email
           invalid_data = self.user_data.copy()
           invalid_data['mail'] = 'invalid-email'

           user = TestUser(**invalid_data)
           with self.assertRaises(ValidationError):
               user.full_clean()

       @patch('ldaporm.models.get_ldap_connection')
       def test_user_save(self, mock_connection):
           """Test user save to LDAP."""
           mock_conn = Mock()
           mock_connection.return_value = mock_conn

           user = TestUser(**self.user_data)
           user.save()

           # Verify LDAP add was called
           mock_conn.add_s.assert_called_once()

       def test_binary_field_handling(self):
           """Test binary field handling."""
           user = TestUser(**self.user_data)
           user.photo = b'test_photo_data'

           # Test serialization
           self.assertEqual(user.photo, b'test_photo_data')

           # Test null handling
           user.photo = None
           self.assertIsNone(user.photo)

This testing guide provides a comprehensive overview of how to author and run tests for the django-ldaporm project, ensuring code quality and reliability.
