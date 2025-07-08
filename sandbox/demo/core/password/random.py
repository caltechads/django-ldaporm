import string
from random import choice
from typing import Final


class RandomPassword:
    """
    Class for generating random passwords and phonetic spellings.

    This class provides methods to generate random passwords of a specified length
    and to convert passwords into phonetic representations (e.g., "A" becomes
    "Alpha") for easier communication.

    """

    #: A mapping of characters to their phonetic spelling
    char_map: Final[dict[str, str]] = {
        "A": "Alpha",
        "B": "Bravo",
        "C": "Charlie",
        "D": "Delta",
        "E": "Echo",
        "F": "Foxtrot",
        "G": "Golf",
        "H": "Hotel",
        "I": "India",
        "J": "Juliet",
        "K": "Kilo",
        "L": "Lima",
        "M": "Mike",
        "N": "November",
        "O": "Oscar",
        "P": "Papa",
        "Q": "Quebec",
        "R": "Romeo",
        "S": "Sierra",
        "T": "Tango",
        "U": "Uniform",
        "V": "Victor",
        "W": "Whiskey",
        "X": "X-ray",
        "Y": "Yankee",
        "Z": "Zulu",
    }

    #: The set of punctuation characters to use in the password
    punctuation: str = "!#$&()*,-./:;<>?@[]^"

    #: The length of the password to generate
    size: int = 10

    def get_random_password(self) -> str:
        """
        Generate a random password that satisfies our password length.

        Returns:
            The generated password

        """
        return "".join(
            [
                choice(string.ascii_letters + string.digits)  # noqa: S311
                for _ in range(RandomPassword.size)
            ]
        )

    def get_phonetic_strings(self, password: str) -> list[str]:
        """
        Given a password, return a list of strings that represent the phonetic
        pronunciation of the password.

        Args:
            password: the password for which to generate phonetic strings

        Returns:
            A list of strings that represent the phonetic pronunciation of the
            password

        """
        strings = []
        for char in password:
            if char.isdigit():
                strings.append(f"Number ({char})")
            elif char.upper() in RandomPassword.char_map:
                case = "Upper" if char.isupper() else "Lower"
                mapping = RandomPassword.char_map[char.upper()]
                strings.append(f"{case} case ({char}) as in {mapping}")
        return strings
