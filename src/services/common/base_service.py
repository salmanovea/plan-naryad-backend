import re
from typing import Any, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class BaseService:
    """
    A base service class with general-purpose helpers for mapping ORM objects
    and query results into Pydantic schemas. Concrete services inherit from it.
    """

    @staticmethod
    def map_obj_to_schema(obj, schema_cls: Type[BaseModel]) -> BaseModel:
        """
        Map an object's attributes to an instance of the given Pydantic schema.

        :param obj: The object to map to the schema.
        :param schema_cls: The schema class to map the object to.
        :return: An instance of the schema populated with the object's data.
        """
        obj_dict = {key: getattr(obj, key) for key in schema_cls.model_fields.keys()}
        return schema_cls(**obj_dict)

    @staticmethod
    def map_nested_fields(
        obj: Any,
        schema_class: Type[BaseModel] | None,
        field_base: str,
    ) -> dict[str, Any] | None:
        """
        Map nested fields from an object's attributes into a dict based on the schema.

        Each field in `schema_class` is read from `obj` as `<field_base>_<field>`.
        Returns None if every looked-up attribute is None.
        """
        if schema_class is None:
            return None
        mapped_data = {}
        filled = False
        for field, field_type in schema_class.model_fields.items():
            model_field_value = getattr(obj, f"{field_base}_{field}", None)

            mapped_data[field] = model_field_value
            if model_field_value is not None:
                filled = True

        return mapped_data if filled else None

    @staticmethod
    def _natural_sort_key(value):
        """
        Build a key for natural sorting (text and numbers in a human-friendly order).

        Numeric fragments are compared as integers, not strings.
        """

        def convert(text):
            return int(text) if text.isdigit() else text.lower()

        return [convert(chunk) for chunk in re.split(r"(\d+)", value)]

    @staticmethod
    def map_aggregated_array_fields(
        obj: Any,
        prefix: str,
        schema_cls: Type[T],
        suffixes: tuple[str, ...] = ("ids", "names", "sort_orders"),
    ) -> list[T]:
        """
        Map aggregated array fields (e.g. `<prefix>_ids`, `<prefix>_names`, ...) into
        a list of `schema_cls` instances.

        Used when a SQL query returns multiple parallel array columns that belong to
        the same child entity.
        """
        arrays = [getattr(obj, f"{prefix}_{suffix}", []) or [] for suffix in suffixes]

        max_len = max(len(arr) for arr in arrays)
        normalized_arrays = [arr if len(arr) == max_len else arr + [None] * (max_len - len(arr)) for arr in arrays]

        items = []
        for i in range(max_len):
            data = {}
            for j, field in enumerate(schema_cls.model_fields.keys()):
                data[field] = normalized_arrays[j][i] if j < len(normalized_arrays) else None

            if any(value is not None for value in data.values()):
                items.append(schema_cls(**data))

        return items
