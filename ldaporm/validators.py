import re
from typing import Any

from django.core import validators


class EmailForwardValidator:  # noqa: PLW1641
    """
    Matches either a username:

        foo

    or a full email address

        foo@example.com

    Keyword Args:
        message: The message to display when the validation fails.
        code: The code to display when the validation fails.

    """

    #: The message to display when the validation fails.
    message: str = "Enter a valid email address."
    #: The code to display when the validation fails.
    code: str = "invalid"
    #: The regex to match a username.
    NAME_REGEX = re.compile("^[a-z][-a-z0-9]*$")
    #: The list of empty values.
    empty_values: list[Any] = list(validators.EMPTY_VALUES)  # noqa: RUF012

    def __init__(self, message: str | None = None, code: str | None = None) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code

    def _validate_email(self, value: Any) -> None:
        """
        Validate that the input is a valid email address.
        """
        if value in self.empty_values:
            return

        if self.NAME_REGEX.search(value):
            return

        validators.validate_email(value)

    def __call__(self, value: Any) -> None:
        """
        Validate that the input contains either a username or a valid email address.

        Args:
            value: The value to validate.

        """
        if isinstance(value, list):
            for item in value:
                self._validate_email(item)
            return

        self._validate_email(value)

    def __eq__(self, other: object) -> bool:
        """
        Check if two EmailForwardValidator instances are equal.

        They are equal when:

        - they are both :py:class:`EmailForwardValidator` instances
        - the message is the same
        - the code is the same

        Args:
            other: The other EmailForwardValidator instance to compare with.

        Returns:
            True if the instances are equal, False otherwise.

        """
        if not isinstance(other, EmailForwardValidator):
            return False

        return self.message == other.message and self.code == other.code


validate_email_forward = EmailForwardValidator()
