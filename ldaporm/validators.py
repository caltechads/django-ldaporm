import re
from typing import Any, List

from django.core import validators


class EmailForwardValidator:

    """
    Matches either a username:

        foo

    or a full email address

        foo@example.com
    """
    message: str = 'Enter a valid email address.'
    code: str = 'invalid'
    NAME_REGEX = re.compile("^[a-z][-a-z0-9]*$")
    empty_values: List[Any] = list(validators.EMPTY_VALUES)

    def __init__(self, message: str = None, code: str = None) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code

    def __call__(self, value: Any) -> None:
        """
        Validate that the input contains either a username or a valid email address.
        """
        if value in self.empty_values:
            return

        if self.NAME_REGEX.search(value):
            return

        validators.validate_email(value)

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, EmailForwardValidator) and
            (self.message == other.message) and
            (self.code == other.code)
        )


validate_email_forward = EmailForwardValidator()
