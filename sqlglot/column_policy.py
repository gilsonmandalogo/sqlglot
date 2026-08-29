from __future__ import annotations

import typing as t
from collections.abc import Iterable, Mapping

from sqlglot import expressions as exp
from sqlglot.dialects.dialect import Dialect, DialectType
from sqlglot.schema import normalize_name


class ColumnPolicy:
    """
    Names sensitive columns as ``(catalog, db, table, column)`` paths and checks
    whether a given table/column is covered.

    Identifier comparison uses the same dialect normalization rules as
    :func:`sqlglot.schema.normalize_name` / :func:`sqlglot.optimizer.normalize_identifiers.normalize_identifiers`
    (for example Postgres lowercases unquoted identifiers, Snowflake uppercases them,
    and quoted identifiers keep their case).
    """

    def __init__(
        self,
        columns: Iterable[str] | Mapping[str, t.Any] | None = None,
        dialect: DialectType = None,
    ) -> None:
        self._dialect: Dialect = Dialect.get_or_raise(dialect)
        self._entries: set[tuple[str, ...]] = set()

        if columns is None:
            return

        if isinstance(columns, Mapping):
            for name in columns:
                self.add(name)
        else:
            for name in columns:
                self.add(name)

    @property
    def dialect(self) -> Dialect:
        return self._dialect

    def add(self, column: str | exp.Column, dialect: DialectType = None) -> ColumnPolicy:
        """
        Register a sensitive column path such as ``users.email`` or
        ``catalog.db.table.col``.

        Args:
            column: A dotted column path string or a :class:`~sqlglot.expressions.Column`.
            dialect: Optional dialect override used when parsing/normalizing ``column``.

        Returns:
            ``self``, so calls can be chained.
        """
        parts = self._normalize_column_parts(column, dialect=dialect)
        if len(parts) < 2:
            raise ValueError(
                f"Column policy entries require at least table.column, got: {'.'.join(parts) or column!r}"
            )
        self._entries.add(parts)
        return self

    def covers(
        self,
        table: str | exp.Table | exp.Column | None = None,
        column: str | exp.Column | None = None,
        dialect: DialectType = None,
    ) -> bool:
        """
        Return whether this policy covers the given table/column.

        Forms:
            - ``covers("users.email")`` — a single dotted column path
            - ``covers("users", "email")`` / ``covers(table="users", column="email")``
            - ``covers("db.users", "email")`` — partially qualified table plus column

        Matching aligns path parts from the right (column side). An entry covers a
        lookup when the overlapping suffix of length ≥ 2 (table + column) is equal
        after dialect normalization. So ``users.email`` covers ``catalog.db.users.email``
        and vice versa, but not ``other.email``.
        """
        query = self._query_parts(table, column, dialect=dialect)
        if len(query) < 2:
            return False

        return any(self._matches(entry, query) for entry in self._entries)

    def __contains__(self, item: object) -> bool:
        if not isinstance(item, (str, exp.Column)):
            return False
        return self.covers(item)

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> t.Iterator[tuple[str, ...]]:
        return iter(self._entries)

    def _query_parts(
        self,
        table: str | exp.Table | exp.Column | None,
        column: str | exp.Column | None,
        dialect: DialectType = None,
    ) -> tuple[str, ...]:
        if column is None:
            if table is None:
                raise TypeError("covers() requires a column path or table and column")
            if not isinstance(table, (str, exp.Column)):
                raise TypeError("Expected a column path string or Column")
            return self._normalize_column_parts(table, dialect=dialect)

        if table is None:
            raise TypeError("covers() requires a table when column is given separately")
        if not isinstance(table, (str, exp.Table)):
            raise TypeError("Expected a table path string or Table")

        table_parts = self._normalize_table_parts(table, dialect=dialect)
        column_parts = self._normalize_column_parts(column, dialect=dialect)

        # A multi-part column path already includes its table; use it as-is.
        if len(column_parts) >= 2:
            return column_parts

        return table_parts + column_parts

    def _normalize_column_parts(
        self, column: str | exp.Column, dialect: DialectType = None
    ) -> tuple[str, ...]:
        dialect = Dialect.get_or_raise(dialect or self._dialect)

        expression = exp.to_column(column, dialect=dialect) if isinstance(column, str) else column
        if not isinstance(expression, exp.Column):
            raise TypeError(f"Expected a column path, got {type(expression).__name__}")

        parts = [part for part in expression.parts if isinstance(part, exp.Identifier)]
        return tuple(
            normalize_name(part, dialect=dialect, is_table=i < len(parts) - 1).name
            for i, part in enumerate(parts)
        )

    def _normalize_table_parts(
        self, table: str | exp.Table, dialect: DialectType = None
    ) -> tuple[str, ...]:
        dialect = Dialect.get_or_raise(dialect or self._dialect)

        expression = exp.to_table(table, dialect=dialect) if isinstance(table, str) else table
        if not isinstance(expression, exp.Table):
            raise TypeError(f"Expected a table path, got {type(expression).__name__}")

        return tuple(
            normalize_name(part, dialect=dialect, is_table=True).name
            for part in expression.parts
            if isinstance(part, exp.Identifier)
        )

    @staticmethod
    def _matches(entry: tuple[str, ...], query: tuple[str, ...]) -> bool:
        n = min(len(entry), len(query))
        if n < 2:
            return False
        return entry[-n:] == query[-n:]
