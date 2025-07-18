from typing import TYPE_CHECKING, cast

from demo.core.ldap.models import LDAPUser

from .random import RandomPassword
from .validator import RandomPasswordValidator, ValidationException

if TYPE_CHECKING:
    from ldaporm.managers import LdapManager


class NoSuchUserException(Exception):
    """
    Exception raised when a requested user cannot be found.

    Attributes:
        value: The username or identifier that couldn't be found

    """

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class PasswordConfirmationException(ValidationException):
    """
    Exception raised when password confirmation does not match the new password.

    Attributes:
        error: The error message to display to the user

    """

    error = (
        "The entered new password and password confirmation do not match. "
        "Please re-enter."
    )


class PasswordResetException(ValidationException):
    """
    Exception raised when there is an error resetting a password.

    Attributes:
        error: The error message to display to the user
        passwordServer: The server where the password reset failed

    """

    error = "There was an error resetting the password."

    def __init__(self, passwordServer: str) -> None:  # noqa: N803
        super().__init__()
        self.passwordServer = passwordServer


class BasePasswordChanger:
    """
    Offers a common interface for forcing password changes to a password that we
    generate automatically.

    We need this functionality when resetting passwords for both full
    ``capCaltechOrgPerson`` access.caltech accounts and for simple POSIX
    accounts.

    How you actually set the password on the user object(s) differs from case to
    case, which is why the ``forceResetPassword`` is left to be implemented
    by the subclass.
    """

    def generate_random_password(self) -> tuple[str, list[str]]:
        """
        Generate a random password that satisfies our password requirements
        and return it and the phonetic (Alpha, Bravo, Charlie, etc.) spelling
        for it.  The phonetic spelling is used by Help Desk folk when reading
        the password to the user over the phone.

        Returns:
            A tuple of the password and the phonetic spelling of the password

        """
        rnd = RandomPassword()
        password = rnd.get_random_password()
        return (password, rnd.get_phonetic_strings(password))

    def set_random_password(self, username: str) -> tuple[str, list[str]]:
        """
        Set a random password that satisfies our password requirements
        and on the user object for ``username``.

        :param username: the username of the user on which to set the password
        """
        (password, phonetic_strings) = self.generate_random_password()
        self.force_set_password(username, password)
        return (password, phonetic_strings)


class PasswordChanger(BasePasswordChanger):
    """
    Manage passwords for a full access.caltech, capCaltechOrgPerson type user
    account in CAP LDAP, ldap-auth and AD.
    """

    def _reset_password_no_fallback(self, username: str, password: str) -> None:
        """
        Set the ``CAPPaswordResetRequired`` attribute on CAPPerson, and we do
        not fall back to the previous password if there's a problem setting the
        password in any of the backends (because we don't know the previous
        password.)

        Args:
            username: the username of the user for whom we're setting the password
            password: the password to set

        """
        if not cast("LdapManager", LDAPUser.objects).reset_password(username, password):
            msg = f'Failed to reset password for "{username}"'
            raise ValidationException(msg)

    def force_set_password(self, username: str, password: str) -> None:
        """
        Used to set reset a password by Help Desk itself.

        This resets the password and sets the ``CAPPasswordResetRequired`` flag
        on the CAPPerson object, forcing the user to set a new password at next
        login.

        Args:
            username: the username of the user for whom we're setting the password
            password: the password to set

        """
        if not cast("LdapManager", LDAPUser.objects).reset_password(username, password):
            msg = f'Failed to reset password for "{username}"'
            raise ValidationException(msg)

    def verify_password(self, username: str, password: str) -> bool:
        """
        Try to bind to the LDAP server as the user ``username`` with password
        ``password`` and report on whether the bind succeeded.

        Args:
            username: the username of the user for whom we're setting the password
            password: the password to set

        Returns:
            A boolean indicating whether the bind succeeded.

        """
        return cast("LdapManager", LDAPUser.objects).authenticate(username, password)
