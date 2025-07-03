Development Guide
=================

This guide covers the development workflow for django-ldaporm contributors.

Setting Up the Development Environment
------------------------------------

Clone the repository:

.. code-block:: bash

   git clone https://github.com/your-repo/django-ldaporm.git
   cd django-ldaporm

Install development dependencies:

.. code-block:: bash

   # Using uv (recommended)
   uv sync --dev

   # Or using pip
   pip install -e ".[dev]"

Install pre-commit hooks:

.. code-block:: bash

   pre-commit install

Code Style and Standards
-----------------------

django-ldaporm follows these coding standards:

* **Python**: PEP 8 with Ruff formatting and linting
* **Type Hints**: Python 3.10+ syntax (use `|` instead of `Union`)
* **Docstrings**: Sphinx Napoleon format
* **Imports**: Use built-in types instead of typing imports

Code Formatting
^^^^^^^^^^^^^^^

Format your code with Ruff:

.. code-block:: bash

   ruff format ldaporm/

Type Checking
^^^^^^^^^^^^^

Run type checking with mypy:

.. code-block:: bash

   mypy ldaporm/

Linting
^^^^^^^

Run linting with ruff:

.. code-block:: bash

   ruff check ldaporm/
   ruff check --fix ldaporm/

Testing
-------

.. note::

   We use like pytest for testing, but don't have any tests yet.

Run the test suite:

.. code-block:: bash

   pytest

Documentation
------------

Build the documentation:

.. code-block:: bash

   cd doc
   make html

View the documentation:

.. code-block:: bash

   # Open doc/build/html/index.html in your browser
   open doc/build/html/index.html

Adding New Features
------------------

When adding new features:

1. **Fork in GitHub**:

   Fork the repository in GitHub and clone it locally

2. **Write tests first** (TDD approach):

   .. code-block:: python

      # tests/test_new_feature.py
      def test_new_feature():
          # Write your test
          pass

3. **Implement the feature**:
   .. code-block:: python

      # ldaporm/new_feature.py
      def new_feature():
          # Implement your feature
          pass

4. **Add documentation**:
   - Update docstrings in Sphinx Napoleon format
   - Add examples to the documentation
   - Update the API reference

5. **Run all checks**:
   .. code-block:: bash

      ruff check ldaporm/
      ruff check --fix ldaporm/
      mypy ldaporm/
      pytest

6. **Create a pull request** with a clear description


Release Process
---------------

1. **Update version**:
   .. code-block:: bash

      bumpversion patch  # or minor/major

2. **Update changelog**:

   - Add release notes
   - Document breaking changes


4. **Build and upload to PyPI**:

   .. code-block:: bash

      make release

Contributing Guidelines
-----------------------

* Follow the existing code style
* Write comprehensive tests
* Add proper type hints
* Document all public APIs
* Keep commits atomic and well-described
* Use conventional commit messages

Getting Help
------------

* Check the existing documentation
* Look at existing tests for examples
* Open an issue for bugs or feature requests
* Join the development discussions