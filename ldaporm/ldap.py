# This file is here so that we can patch the ldap module in our tests.
# python-ldap-faker doesn't support patching the ldap module, so we need to
# patch it here.
import ldap
from ldap import *  # noqa: F403

__version__ = ldap.__version__
