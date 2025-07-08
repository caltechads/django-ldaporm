#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        msg = (
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        )
        raise ImportError(msg) from exc

    # This allows easy placement of apps within the interior seedling directory.
    current_path = os.path.dirname(os.path.abspath(__file__))  # noqa: PTH100, PTH120
    sys.path.append(os.path.join(current_path, "demo"))  # noqa: PTH118

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
