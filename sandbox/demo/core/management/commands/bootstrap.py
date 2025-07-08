from demo.logging import logger
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.loader import MigrationLoader


class Command(BaseCommand):
    """
    Do our initial migrate and data load if necessary.

    If `settings.BOOTSTRAP_ALWAYS_MIGRATE` is `True`, always run migrations.
    """

    def db_is_fresh(self, database):
        """
        Figure out if we've never run migrations here.

        Assume that if the contenttypes.0001_initial migration has not run,
        we have a fresh database.
        """
        connection = connections[database]
        loader = MigrationLoader(connection)
        return ("contenttypes", "0001_initial") not in loader.applied_migrations

    def handle(self, **options):  # noqa: ARG002
        logger.info("migrate.start")
        if self.db_is_fresh(DEFAULT_DB_ALIAS):
            call_command("migrate")
            call_command("loaddata", "users")
        elif settings.BOOTSTRAP_ALWAYS_MIGRATE:
            call_command("migrate")
        logger.info("migrate.end")
