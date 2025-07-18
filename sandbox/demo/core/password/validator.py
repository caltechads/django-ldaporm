import re
from re import Pattern
from typing import TYPE_CHECKING, ClassVar, Final, cast

from demo.core.ldap.models import LDAPUser

if TYPE_CHECKING:
    from ldaporm.managers import LdapManager


class ValidationException(Exception):
    """
    Exception raised when password validation fails.

    This exception includes specific error codes and messages for different
    types of validation failures.

    Args:
        code: The specific error code for this validation failure

    """

    errors: Final[dict[str, str]] = {
        "generic": "Password validation error",
        "length": (
            "Please select a password that is at least ten (10) characters in length."
        ),
        "need-non-alpha": (
            "Please select a password that contains at least one (1) "
            "non-alphabetic character."
        ),
        "need-alpha": (
            "Please select a password that contains at least (1) alphabetic "
            "characters each in upper and lower case."
        ),
        "restricted": (
            "Please select a password that does not contain double "
            'quote ("), plus (+), equal (=) or percent (%) characters.'
        ),
        "forbidden-words": (
            "Please select a password that does not contain your username, first name, "
            "last name, or full middle name."
        ),
        "invalid-current": "Invalid current password.",
        "must-be-different": (
            "Your new password must be different than your current password."
        ),
    }

    def __init__(self, code: str = "generic") -> None:
        self.code = code

    def __str__(self) -> str:
        return self.errors[self.code]


class AbstractValidationRule:
    """
    Abstract base class for password validation rules.

    This class defines the interface for all password validation rules.
    Subclasses must implement the validate method.
    """

    def validate(self, old_password: str, new_password: str, username: str) -> None:
        """
        Validate a password against this rule.

        Args:
            old_password: The user's current password
            new_password: The proposed new password
            username: The username of the user

        Raises:
            ValidationException: If the password fails this validation rule

        """
        raise NotImplementedError


class OldPasswordIsNotEmpty(AbstractValidationRule):
    """
    Validation rule that ensures the old password is not empty.

    This rule checks that the old password contains at least one non-whitespace
    character.
    """

    def validate(
        self,
        old_password: str,
        new_password: str,  # noqa: ARG002
        username: str,  # noqa: ARG002
    ) -> None:
        """
        Validate that the old password is not empty.

        Args:
            old_password: The user's current password
            new_password: The proposed new password (unused)
            username: The username of the user (unused)
            **kwargs: Additional context for validation (unused)

        Raises:
            ValidationException: If the old password is empty or contains only
                whitespace

        """
        if not old_password.strip():
            msg = "length"
            raise ValidationException(msg)


class OldPasswordIsCorrect(AbstractValidationRule):
    """
    Validation rule that ensures the old password is correct.

    This rule authenticates the user with the provided old password to verify it
    is correct.
    """

    def validate(
        self,
        old_password: str,
        new_password: str,  # noqa: ARG002
        username: str,
    ) -> None:
        """
        Validate that the old password is correct.

        Args:
            old_password: The user's current password
            new_password: The proposed new password (unused)
            username: The username of the user
            **kwargs: Additional context for validation (unused)

        Raises:
            ValidationException: If authentication with the old password fails

        """
        if not cast("LdapManager", LDAPUser.objects).authenticate(
            username, old_password
        ):
            msg = "invalid-current"
            raise ValidationException(msg)


class OldAndNewPasswordsDiffer(AbstractValidationRule):
    """
    Validation rule that ensures the new password differs from the old one.

    This rule checks that the new password is not identical to the old password.
    """

    def validate(
        self,
        old_password: str,
        new_password: str,
        username: str,  # noqa: ARG002
    ) -> None:
        """
        Validate that the new password is different from the old password.

        Args:
            old_password: The user's current password
            new_password: The proposed new password
            username: The username of the user (unused)

        Raises:
            ValidationException: If the new password is identical to the old password

        """
        if old_password == new_password:
            msg = "must-be-different"
            raise ValidationException(msg)


class NewPasswordIsNotEmpty(AbstractValidationRule):
    """
    Validation rule that ensures the new password is not empty.

    This rule checks that the new password contains at least one non-whitespace
    character.
    """

    def validate(
        self,
        old_password: str,  # noqa: ARG002
        new_password: str,
        username: str,  # noqa: ARG002
    ) -> None:
        """
        Validate that the new password is not empty.

        Args:
            old_password: The user's current password (unused)
            new_password: The proposed new password
            username: The username of the user (unused)

        Raises:
            ValidationException: If the new password is empty or contains only
                whitespace

        """
        if not new_password.strip():
            msg = "length"
            raise ValidationException(msg)


class NewPasswordLengthIsOK(AbstractValidationRule):
    """
    Validation rule that ensures the new password has an acceptable length.

    This rule checks that the new password is between MIN_LENGTH and MAX_LENGTH
    characters.
    """

    #: The minimum allowable length of a password
    MIN_LENGTH: Final[int] = 10

    def validate(
        self,
        old_password: str,  # noqa: ARG002
        new_password: str,
        username: str,  # noqa: ARG002
    ) -> None:
        """
        Validate that the new password length is within the acceptable range.

        Args:
            old_password: The user's current password (unused)
            new_password: The proposed new password
            username: The username of the user (unused)

        Raises:
            ValidationException: If the new password length is less than MIN_LENGTH

        """
        if len(new_password) < self.MIN_LENGTH:
            msg = "length"
            raise ValidationException(msg)


class NewPasswordContentsAreOk(AbstractValidationRule):
    """
    Validation rule that ensures the new password has acceptable content.

    This rule performs multiple checks on the password content, including:
    - Checking for restricted characters (quote, plus, equal, percent)
    - Ensuring it contains at least one lowercase alphabetic character
    - Ensuring it contains at least one uppercase alphabetic character
    - Ensuring it contains at least one numeric character
    - Ensuring it has characters from all three character classes
    - Ensuring it doesn't contain forbidden words (username, first/last name, etc.)

    """

    #: A regular expression that matches restricted characters in a password
    RESTRICTED_CHARS_RE: Final[Pattern] = re.compile('["%=+]')
    #: A regular expression that matches at least two alphabetic characters
    ALPHA_RE: Final[Pattern] = re.compile("(?=.*[a-zA-Z].*[a-zA-Z])")
    #: A regular expression that matches non-alphabetic characters
    NON_ALPHA_RE: Final[Pattern] = re.compile("[^a-zA-Z]")
    #: A list of regular expressions that match specific character classes
    SPECIFIC_CHARS_RE: Final[list[Pattern]] = [
        re.compile(r"[a-z]"),  # at least 1 lowercase letter
        re.compile(r"[A-Z]"),  # at least 1 uppercase letter
        re.compile(r"[0-9]"),  # at least 1 number
    ]
    #: Minimum number of character classes that must be present in the password
    MIN_CHAR_CLASSES: Final[int] = 3
    #: Min length of a password to check for restricted characters instead
    #: of character classes
    PASSWORD_LENGTH_BREAKPOINT: Final[int] = 20

    def check_forbidden_words(self, password: str, user: LDAPUser) -> None:
        """
        A validation method that throws an error if the user's first name, last
        name, middle name, username, or employee number is incorporated into the
        password by pulling those attributes from the user's person object
        and doing a string comparison.

        Args:
            password: the password input by the user
            user: the user's person object

        Raises:
            PasswordForbiddenWordException: if the password contains the user's
                first name, last name, middle name, username, or Caltech UID

        """
        forbidden_words = [
            user.uid.lower(),
            user.last_name.lower(),
        ]
        # the person may not have an employee number
        if hasattr(user, "employee_number") and user.employee_number:
            forbidden_words.append(str(user.employee_number))
        # the person may not have a first name
        if hasattr(user, "first_name") and user.first_name:
            forbidden_words.append(user.first_name.lower())
        for word in forbidden_words:
            if len(word) > 2:  # noqa: PLR2004
                if word in password.lower():
                    msg = "forbidden-words"
                    raise ValidationException(msg)

    def check_restricted_set(self, password: str) -> None:
        """
        Check for restricted characters in the password.

        Args:
            password: the password input by the user

        Raises:
            ValidationException: if the password contains restricted characters

        """
        if self.RESTRICTED_CHARS_RE.search(password):
            msg = "restricted"
            raise ValidationException(msg)

    def check_character_sets(self, password: str) -> None:
        """
        Check that the password contains at least two alphabetic characters, at
        least one non-alphabetic character, and at least three of the four
        character classes: uppercase letters, lowercase letters, numbers, and
        non-alphanumeric characters.

        Args:
            password: the password input by the user

        Raises:
            ValidationException: The password does not meet the requirements

        """
        # At least two letters
        if not self.ALPHA_RE.search(password):
            msg = "need-alpha"
            raise ValidationException(msg)
        self.check_restricted_set(password)
        # At least one non-letter
        if not self.NON_ALPHA_RE.search(password):
            msg = "need-non-alpha"
            raise ValidationException(msg)

        count = 0
        for pattern in self.SPECIFIC_CHARS_RE:
            if pattern.search(password):
                count = count + 1

        if count < self.MIN_CHAR_CLASSES:
            msg = "char-class"
            raise ValidationException(msg)

    def validate(
        self,
        old_password: str,  # noqa: ARG002
        new_password: str,
        username: str,
    ) -> None:
        """
        Validate the new password.

        If the password is less than 20 characters, we check for restricted
        characters and character classes.  If it is 20 characters or longer, we
        check for restricted sets of characters.

        Args:
            old_password: the user's current password (unused)
            new_password: the new password
            username: the user's username (unused)
            **kwargs: additional keyword arguments

        """
        user = cast("LdapManager", LDAPUser.objects).get(uid=username)
        self.check_forbidden_words(new_password, user)
        self.check_character_sets(new_password)


class AbstractPasswordValidator:
    """
    Abstract base class for password validators.

    A password validator applies a sequence of validation rules to verify
    that a password meets all requirements.

    """

    #: The list of validation rule classes to apply
    rules: ClassVar[list[type[AbstractValidationRule]]]

    def validate(self, old_password: str, new_password: str, username: str) -> None:
        for rule in self.rules:
            rule().validate(old_password, new_password, username)


class PasswordValidator(AbstractPasswordValidator):
    """
    The validator we use when the user knows their old password.
    """

    rules: ClassVar[list[type[AbstractValidationRule]]] = [
        NewPasswordIsNotEmpty,
        OldPasswordIsNotEmpty,
        OldPasswordIsCorrect,
        OldAndNewPasswordsDiffer,
        NewPasswordLengthIsOK,
        NewPasswordContentsAreOk,
    ]


class ForcedResetPasswordValidator(AbstractPasswordValidator):
    """
    The validator we use when someone has used access.caltech Help Desk to force
    reset a user's password.  In this case, we don't know the old password.
    """

    rules: ClassVar[list[type[AbstractValidationRule]]] = [
        NewPasswordIsNotEmpty,
        NewPasswordLengthIsOK,
        NewPasswordContentsAreOk,
    ]


class RandomPasswordValidator(AbstractPasswordValidator):
    """
    The validator we use when we're generating a random password.
    """

    rules: ClassVar[list[type[AbstractValidationRule]]] = [
        NewPasswordIsNotEmpty,
        NewPasswordLengthIsOK,
        NewPasswordContentsAreOk,
    ]
