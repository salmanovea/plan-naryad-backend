from typing import (
    Any,
    Callable,
    ClassVar,
    Generic,
    Iterable,
    List,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
)
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import (
    Select,
    case,
    cast,
    column,
    delete,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only
from sqlalchemy.sql import Executable
from sqlalchemy.sql.elements import BinaryExpression, ColumnElement
from sqlalchemy.sql.sqltypes import DECIMAL
from sqlalchemy.sql.sqltypes import String as StringType

from src.api.schemes import PaginationParams
from src.config.logger import LoggerProvider
from src.models.dbo.models import Base
from src.utils.helpers import get_paginated_query, safe_ilike

T = TypeVar("T", bound=Base)
V = TypeVar("V")

log = LoggerProvider().get_logger(__name__)

SEARCH_OPERATORS = {
    "ilike": safe_ilike,
    "exact": lambda col, val: col == val,
    "startswith": lambda col, val: col.ilike(f"{val}%"),
    "endswith": lambda col, val: col.ilike(f"%{val}"),
    "gt": lambda col, val: col > val,
    "gte": lambda col, val: col >= val,
    "lt": lambda col, val: col < val,
    "lte": lambda col, val: col <= val,
    "uuid": lambda col, val: col == val,
    "date": lambda col, val: func.date(col) == val,
    "in": lambda col, val: col.in_(val if isinstance(val, list) else [val]),
    "not_in": lambda col, val: ~col.in_(val if isinstance(val, list) else [val]),
    "is_null": lambda col, val: col.is_(None) if val else col.is_not(None),
}


class DictToObject:
    def __init__(self, dictionary):
        for key, value in dictionary.items():
            setattr(self, key, value)


class BaseManager(Generic[T]):
    """
    A generic base manager for handling common database operations like
    creating, retrieving, updating, deleting, and filtering entities.
    """

    entity: Type[T]

    join_columns: Optional[dict] = None
    _special_filters_map: ClassVar[Optional[dict[str, dict[str, Any]]]] = None

    def __init__(self, db: AsyncSession):
        self.db = db

    def get_options_base_query(self) -> Select:
        """
        Return a base query for the entity used by options endpoints.

        Must be overridden by subclasses that need it.
        """
        raise NotImplementedError("Options query for this entity not implemented")

    def get_base_query(self) -> Select:
        """
        Return a base query for the entity.

        Override it when `filter_by_related_entity_id` is used for a manager.
        """
        query = select(self.entity)
        return query

    async def create(self, payload: dict, commit: bool = True) -> T:
        """Create a new entity and optionally commit."""
        new_entity = self.entity(**payload)
        self.db.add(new_entity)
        if commit:
            await self.db.commit()
            await self.db.refresh(new_entity)
        return new_entity

    async def get_by_entity_id(
        self,
        entity_class: Type[V],
        entity_id: Union[int, UUID],
    ) -> Optional[V]:
        """Fetch an entity of any given class by id."""
        return await self.db.get(entity_class, entity_id)

    async def get_by_id(self, entity_id: Union[int, UUID]) -> Optional[T]:
        """Fetch the manager's entity by id."""
        return await self.db.get(self.entity, entity_id)

    async def get_by_id_with_specified_fields(
        self,
        entity_id: Union[int, UUID],
        fields: list[str],
        key_field: str = "id",
    ) -> Optional[T]:
        """Fetch an entity by id loading only the specified columns."""
        if key_field not in fields:
            fields.append(key_field)

        query = (
            select(self.entity)
            .options(load_only(*[getattr(self.entity, field) for field in fields]))
            .where(getattr(self.entity, key_field) == entity_id)
        )
        result = await self.db.execute(query)

        return result.scalar_one_or_none()

    async def get_by_ids(
        self,
        entity_ids: Iterable[Union[int, UUID]],
    ) -> List[T]:
        """Fetch multiple entities by their ids; returns [] for empty input."""
        entity_ids = list(entity_ids)

        if not entity_ids:
            return []

        query = select(self.entity).where(self.entity.id.in_(entity_ids))
        result = await self.db.execute(query)
        rows = result.scalars().all()
        return list(rows)

    async def update_by_id(
        self,
        entity_id: Union[int, UUID],
        payload: dict,
        commit: bool = True,
    ) -> Optional[T]:
        """Update an entity by id; returns the updated entity or None."""
        entity = await self.get_by_id(entity_id)
        if entity:
            for key, value in payload.items():
                setattr(entity, key, value)
            if commit:
                await self.db.commit()
                await self.db.refresh(entity)
        return entity

    async def delete_by_id(self, entity_id: Union[int, UUID]) -> None:
        """Delete an entity by id."""
        entity = await self.get_by_id(entity_id)
        if entity:
            await self.db.delete(entity)
            await self.db.commit()

    def _safe_operator(
        self,
        column_expr: ColumnElement,
        op_name: str,
        value: Any,
    ) -> BinaryExpression:
        if hasattr(column_expr, op_name):
            method = getattr(column_expr, op_name)
            if callable(method):
                return method(value)

        if op_name == "overlap":
            return column_expr.op("&&")(value)
        if op_name == "contains":
            return column_expr.op("@>")(value)

        raise AttributeError(f"Column '{column_expr}' does not support operation '{op_name}'")

    def apply_filters_simple(self, query: Select, **filters) -> Select:
        """Apply flat column filters (name / name__gt / name__in / ...) to a Select."""
        for filter_name, filter_value in filters.items():
            if filter_value is None:
                continue
            splitted = filter_name.split("__")
            sign = ""
            match len(splitted):
                case 2:
                    col_name, sign = splitted
                case 1:
                    col_name = splitted[0]
                case _:
                    continue
            col = query.columns.get(col_name)
            if col is None:
                continue
            if sign == "":
                query = query.where(column(col_name) == filter_value)
            else:
                expr = self.__apply_filter_expression(column(col_name), sign, filter_value)
                if expr is not None:
                    query = query.where(expr)
        return query

    def apply__in__filters_as_or(self, query: Select, **filters):
        """Apply only `*__in` filters, chaining them with OR instead of AND."""
        wheres = []
        for filter_name, filter_value in filters.items():
            if filter_value is None:
                continue
            splitted = filter_name.split("__")
            sign = ""
            match len(splitted):
                case 2:
                    col_name, sign = splitted
                case _:
                    continue
            col = query.columns.get(col_name)
            if col is None or sign != "in":
                continue
            expr = self.__apply_filter_expression(column(col_name), sign, filter_value)
            if expr is not None:
                wheres.append(expr)
        if wheres:
            query = query.where(or_(*wheres))
        return query

    def __apply_filter_expression(self, col, sign, filter_value):
        res_col = None
        if sign in {"lt", "le", "gt", "ge", "ne"}:
            res_col = getattr(col, f"__{sign}__")(filter_value)
        elif sign == "gte":
            res_col = col >= filter_value
        elif sign == "lte":
            res_col = col <= filter_value
        elif sign == "in":
            res_col = col.in_(filter_value)
        elif sign == "notin":
            res_col = col.in_(filter_value)
        elif sign == "is":
            res_col = col.is_(filter_value)
        elif sign == "isnot":
            res_col = col.is_not(filter_value)
        elif sign == "like":
            res_col = col.like(filter_value)
        elif sign == "ilike":
            res_col = col.ilike(f"%{filter_value}%")
        elif sign == "isnotnull":
            res_col = col.is_not(None)
        elif sign == "isnull":
            res_col = col.is_(None)
        return res_col

    def _get_filter_bool_expression(self, filter_name: str, filter_value: Any, query: Select):
        """Build a SQLAlchemy boolean expression for a named filter."""
        if self._special_filters_map and filter_name in self._special_filters_map:
            special = self._special_filters_map[filter_name]
            filter_key = special["filter_key"]
            filter_type = special.get("filter_type", "eq")

            if filter_value is None or (isinstance(filter_value, (str, list, set, dict)) and not filter_value):
                return sa.true()

            column_expr = (
                self.join_columns.get(filter_key)
                if self.join_columns and filter_key in self.join_columns
                else getattr(self.entity, filter_key, None)
            )
            if column_expr is None:
                raise ValueError(f"Column '{filter_key}' not found for special filter '{filter_name}'")

            if filter_type == "contains":
                if not isinstance(filter_value, list):
                    filter_value = [filter_value]
                return self._safe_operator(column_expr, "contains", filter_value)

            if filter_type == "overlap":
                return self._safe_operator(column_expr, "overlap", filter_value)

            if filter_type == "eq":
                return column_expr == filter_value

            raise ValueError(f"Unknown filter_type '{filter_type}' in special_filters_map")

        if filter_name in query.columns or (self.join_columns and filter_name in self.join_columns.keys()):
            obj = self.join_columns if self.join_columns and filter_name in self.join_columns else self.entity
            if isinstance(obj, dict):
                obj = DictToObject(obj)  # type: ignore[assignment]

            if not hasattr(obj, filter_name):
                return None

            return getattr(obj, filter_name).__eq__(filter_value)

        split_by_double_underscore = filter_name.split("__")
        sign = split_by_double_underscore.pop()
        col_name = split_by_double_underscore[0]

        obj = self.join_columns if self.join_columns and col_name in self.join_columns else self.entity
        if isinstance(obj, dict):
            obj = DictToObject(obj)  # type: ignore[assignment]

        if sign in {"lt", "le", "gt", "ge", "ne"}:
            return getattr(getattr(obj, col_name), f"__{sign}__")(filter_value)
        elif sign == "gte":
            return getattr(obj, col_name) >= filter_value
        elif sign == "lte":
            return getattr(obj, col_name) <= filter_value
        elif sign == "in":
            return getattr(obj, col_name).in_(filter_value)
        elif sign == "notin":
            return ~getattr(obj, col_name).in_(filter_value)
        elif sign == "is":
            return getattr(obj, col_name).is_(filter_value)
        elif sign == "isnot":
            return getattr(obj, col_name).is_not(filter_value)
        elif sign == "like":
            return getattr(obj, col_name).like(filter_value)
        elif sign == "ilike":
            return getattr(obj, col_name).ilike(f"%{filter_value}%")
        elif sign == "isnotnull":
            return getattr(obj, col_name).is_not(None)
        elif sign == "isnull":
            return getattr(obj, col_name).is_(None)

        raise ValueError(f"Unknown filter name ({filter_name})")

    def apply_filters(self, query: Select, **filters) -> Select:
        """Apply a dict of filters to a Select; None values are skipped."""
        filters = {key: value for key, value in filters.items() if value is not None}
        for filter_name, filter_value in filters.items():
            query = query.where(
                self._get_filter_bool_expression(
                    filter_name=filter_name,
                    filter_value=filter_value,
                    query=query,
                )
            )

        return query

    def add_order_to_query(self, query: Select, order_by: str) -> Select:
        """Apply a single `order_by` clause to the query, respecting `-` for DESC."""
        if order_by.startswith("-"):
            descending = True
            order_by = order_by[1:]
        else:
            descending = False

        obj = self.join_columns if self.join_columns and order_by in self.join_columns else self.entity
        if isinstance(obj, dict):
            obj = DictToObject(obj)  # type: ignore[assignment]

        apply_numeric_sorting_for_tables = ("floor", "section")
        if order_by in query.columns:
            order_by_column = getattr(obj, order_by)
            column_type = getattr(order_by_column, "type", None)
            if self.entity.__tablename__ in apply_numeric_sorting_for_tables and isinstance(column_type, StringType):
                numeric_part = cast(func.substring(order_by_column, r"([0-9]+)"), DECIMAL)
                sort_column = case(
                    (
                        func.regexp_match(order_by_column, r"[0-9]+") is not None,
                        numeric_part,
                    ),
                    else_=None,
                )
                if descending:
                    query = query.order_by(sort_column.desc(), order_by_column.desc())
                else:
                    query = query.order_by(sort_column.asc(), order_by_column.asc())
            else:
                if descending:
                    query = query.order_by(order_by_column.desc())
                else:
                    query = query.order_by(order_by_column.asc())
        return query

    def apply_ordering(self, query: Select, order_by) -> Select:
        """Apply a list of `order_by` clauses to the query."""
        for order_by_param in order_by:
            query = self.add_order_to_query(query, order_by_param)
        return query

    async def count(
        self,
        query: Select = None,
        search: Optional[str] = None,
        group_by_field: Optional[str] = None,
        **filters,
    ) -> int:
        """Count rows matching the filters (optionally grouped by a field)."""
        if query is None:
            query = self.get_base_query()

        query = self.apply_filters(query, **filters)

        if search:
            query = self.apply_full_text_search(query, search)

        if group_by_field:
            subq = query.subquery()
            count_column = getattr(subq.c, group_by_field, None)
            if count_column is None:
                raise ValueError(f"Field '{group_by_field}' not found in query columns")
            count_query = select(func.count(func.distinct(count_column)))
        else:
            count_query = select(func.count()).select_from(query.subquery())

        result = await self.db.execute(count_query)
        return result.scalar()

    async def search(
        self,
        query: Select = None,
        order_by: Optional[list[str]] = None,
        pagination: Optional[PaginationParams] = None,
        with_scalars: bool = True,
        search: Optional[str] = None,
        **filters,
    ) -> List[T]:
        """Search entities with optional filters, ordering, pagination and full-text search."""
        if query is None:
            query = self.get_base_query()

        query = self.apply_filters(query, **filters)

        if search:
            query = self.apply_full_text_search(query, search)

        if order_by:
            query = self.apply_ordering(query, order_by)

        if pagination:
            query = get_paginated_query(query, pagination)
        result = await self.fetch(query, with_scalars)
        return result

    async def bulk_update_by_batch(
        self,
        entities_to_update: list[dict[str, Union[int, UUID, str]]],
        batch: int = 32000,
    ) -> None:
        """Bulk-update a list of entities in batches of `batch` rows."""
        if not entities_to_update:
            return

        if len(entities_to_update) < batch:
            await self.bulk_update(entities_to_update)
        else:
            start, end = 0, batch
            while end < len(entities_to_update):
                await self.bulk_update(entities_to_update[start:end])
                start, end = end, end + batch
            await self.bulk_update(entities_to_update[start:])

    async def bulk_update(
        self,
        entities_to_update: list[dict[str, Union[int, UUID, str]]],
        is_commit: bool = True,
    ):
        """
        Bulk-update entities with new data.

        `entities_to_update` is a list of dicts with 'id' and the fields to set.
        """
        updated_entities = await self.db.execute(
            update(self.entity),
            entities_to_update,
        )
        if is_commit:
            await self.db.commit()

        return updated_entities

    async def bulk_delete(self, entity_ids: list[Union[int, UUID]]) -> None:
        """Delete multiple entities by id in a single statement."""
        if not entity_ids:
            return

        query = delete(self.entity).where(self.entity.id.in_(entity_ids))

        await self.db.execute(query)

    async def bulk_delete_by_batch(
        self,
        entity_ids: list[Union[int, UUID]],
        batch: int = 32000,
    ) -> None:
        """Bulk-delete entities in batches of `batch` ids."""
        if not entity_ids:
            return

        if len(entity_ids) < batch:
            await self.bulk_delete(entity_ids)
        else:
            start, end = 0, batch
            while end < len(entity_ids):
                await self.bulk_delete(entity_ids[start:end])
                start, end = end, end + batch
            await self.bulk_delete(entity_ids[start:])

    async def bulk_insert(self, entities_data: list[dict], is_commit: bool = False) -> None:
        """Bulk-insert a list of dicts as new rows."""
        if not entities_data:
            return

        query = insert(self.entity).values(entities_data)

        await self.db.execute(query)
        if is_commit:
            await self.db.commit()

    async def create_or_update(self, entities: list):
        """For each input entity create a new row (no id) or update by id."""
        updated_entities: list = []
        for entity in entities:
            data_dict = {key: value for key, value in entity.model_dump().items() if key != "id"}
            if entity.id:
                updated_entity = await self.update_by_id(
                    entity_id=entity.id,
                    payload=data_dict,
                )  # type: ignore[func-returns-value]
                updated_entities.append(updated_entity)
            else:
                created_entity: T = await self.create(payload=data_dict)
                updated_entities.append(created_entity)
        return updated_entities

    def _deduplicate_rows(
        self,
        rows: Iterable[Sequence[object]],
        key_func: Optional[Callable[[Sequence[object]], object]] = None,
    ):
        """Deduplicate a list of rows by a hashable key."""
        key_func = key_func if key_func is not None else (lambda row: tuple(str(item) for item in row))

        seen = set()
        unique_rows = []

        for row in rows:
            key = key_func(row)
            if key not in seen:
                seen.add(key)
                unique_rows.append(row)

        return unique_rows

    async def fetch(
        self,
        query,
        with_scalars: bool = True,
        deduplicate: bool = True,
        key_func=None,
    ):
        """Execute a query and return all rows as scalars or raw tuples."""
        result = await self.db.execute(query)

        if with_scalars:
            scalars = result.scalars()
            if deduplicate:
                scalars = scalars.unique()
            return list(scalars.all())
        else:
            rows = result.fetchall()
            if not deduplicate:
                return list(rows)
            return self._deduplicate_rows(rows, key_func)

    async def fetch_val(self, query: Executable) -> V | None:
        """Execute a query and return a single scalar value."""
        result = await self.db.execute(query)
        return result.scalar()

    async def bulk_upsert(
        self,
        data: list[dict],
        key_field: str | list[str],
        update_fields: list[str],
        batch_size: int = 5000,
        is_do_nothing: bool = False,
    ):
        """Bulk-upsert rows in batches using ON CONFLICT DO UPDATE / DO NOTHING."""
        if len(data) == 0:
            return

        start, end = 0, batch_size
        while end < len(data):
            batch_data = data[start:end]
            await self._execute_upsert(batch_data, key_field, update_fields, is_do_nothing=is_do_nothing)

            start = end
            end = end + batch_size

        batch_data = data[start : len(data)]
        await self._execute_upsert(batch_data, key_field, update_fields, is_do_nothing=is_do_nothing)
        await self.db.commit()

    async def _execute_upsert(
        self,
        batch_data: list[dict],
        key_field: str | list[str],
        update_fields: list[str],
        is_do_nothing: bool = False,
    ) -> None:
        if isinstance(key_field, list):
            index_elements = [getattr(self.entity, item) for item in key_field]
        else:
            index_elements = [getattr(self.entity, key_field)]

        insert_stmt = insert(self.entity).values(batch_data)
        if is_do_nothing:
            update_stmt = insert_stmt.on_conflict_do_nothing(
                index_elements=index_elements,
            )
        else:
            update_stmt = insert_stmt.on_conflict_do_update(
                index_elements=index_elements,
                set_={col.name: col for col in insert_stmt.excluded if col.name in update_fields},
            )
        await self.db.execute(update_stmt)

    def apply_full_text_search(
        self,
        query: Select,
        search: str,
    ) -> Select:
        """
        Apply full-text search using the columns declared in `text_search_fields`.

        The subclass should define `text_search_fields = {<column>: <operator>}`,
        where operator is one of SEARCH_OPERATORS keys.
        """
        if not search or not hasattr(self, "text_search_fields"):
            return query

        filters = []

        for col in query.selected_columns:
            if hasattr(col, "name") and col.name in self.text_search_fields:
                op_type = self.text_search_fields[col.name]
                op_func = SEARCH_OPERATORS.get(op_type)
                if op_func:
                    filters.append(op_func(col, search))

        if filters:
            query = query.where(or_(*filters))

        return query
