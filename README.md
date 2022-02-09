# django-ldaporm

`django-ldaporm` provides  Django ORM-like module that allows you to treat ldap object classes like RDBMS tables.  This
allows you to use Django forms, fields and views natively with ldap models.

## Installing django-ldaporm

`django-ldaporm` is a pure python package.  As such, it can be installed in the usual python ways.  For the following
instructions, either install it into your global python install, or use a python 
[virtual environment](https://python-guide-pt-br.readthedocs.io/en/latest/dev/virtualenvs/) to install it without polluting your
global python environment.

### Install via pip

    pip install django-ldaporm

### Install via `setup.py`

Download a release from [Github](https://github.com/caltechads/deployfish/releases), then:

    unzip django-ldaporm-1.0.5.zip
    cd django-ldaporm-1.0.5
    python setup.py install

Or:

    git clone https://github.com/caltechads/django-ldaporm.git
    cd django-ldaporm
    python setup.py install
