from typing import cast

from ldaporm.managers import F, LdapManager
from ldaporm.models import Model


class LdapModelTableMixin:
    """
    A mixin that makes :py:class:`~wildewidgets.BasicModelTable` work with
    :py:class:`ldaporm.models.Model`.
    """

    model: type[Model]

    def search_query(self, qs: F, value: str) -> F | None:
        """
        Build a :py:class:`ldaporm.managers.F` object for performing global
        search across multiple columns.

        This method constructs a query that searches all searchable columns
        for the given value, using OR logic to match records that have the value
        in any searchable column.

        Args:
            qs: The :py:class:`ldaporm.managers.F` object
            value: The search term to look for

        Returns:
            F | None: An ldaporm :py:class:`~ldaporm.managers.F` object
                representing the search, or ``None`` if no searchable columns
                exist

        """
        query: F | None = None
        for column in self.searchable_columns():  # type: ignore[attr-defined]
            attr_name = f"search_{column}_column"
            if hasattr(self, attr_name):
                q = getattr(self, attr_name)(qs, column, value)
            else:
                kwarg_name = f"{column}__icontains"
                q = F(cast("LdapManager", self.model.objects)).filter(
                    **{kwarg_name: value}
                )
            query = query | q if query else q
        return query

    def search(self, qs: F, value: str) -> list[Model]:
        """
        Apply a global search across all searchable columns.

        This method is called when a user enters a search term in the main
        dataTables.js search input. It applies the search across all searchable
        columns and returns distinct results.

        Args:
            qs: The queryset to search
            value: The search term

        Returns:
            models.QuerySet: The filtered queryset containing only matching records

        """
        query = self.search_query(qs, value)
        return cast("LdapManager", self.model.objects).filter(query)
