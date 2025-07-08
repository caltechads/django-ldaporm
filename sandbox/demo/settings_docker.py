import os

os.environ["DB_NAME"] = "fake"
os.environ["DB_USER"] = "fake"
os.environ["DB_PASSWORD"] = "fake"  # noqa: S105
os.environ["DB_HOST"] = "fake"
os.environ["DB_PORT"] = "fake"
os.environ["CACHE"] = "fake"
os.environ["DEVELOPMENT"] = "True"
os.environ["ENABLE_DEBUG_TOOLBAR"] = "True"

from .settings import *  # noqa: F403
