"""Keep opaque Word locators out of model outputs; map short IDs strictly."""

import re
from typing import Literal

from pydantic import Field, create_model, field_validator

from app.model_client import ModelUnavailable


def model_fields(fields):
    """把 Word 内部定位名转换为本批短编号，并唯一标出当前填写位置。

    Args:
        fields: 本次操作关联的字段集合。
    """
    mapping = {f"f{index:03d}": field["name"] for index, field in enumerate(fields, 1)}
    payload = [
        {
            "name": key,
            "label": field.get("display_name") or re.sub(r"·位置.*$", "", field["name"]),
            "context": re.sub(
                r"\{[^{}]+\}",
                "[其他填写处]",
                field.get("context", "").replace("{" + field["name"] + "}", "[当前填写处]", 1),
            ),
            "value_type": field.get("value_type", "text"),
            "component": field.get("component", ""),
            "choices": field.get("choices", []),
            "fixed_unit": field.get("fixed_unit", ""),
        }
        for key, field in zip(mapping, fields)
    ]
    return mapping, payload


def batch_schema(base, item_base, collection_name, mapping):
    """Invalid IDs fail inside structured-output validation and its bounded retry."""
    item = create_model(
        "BatchField", __base__=item_base, field_name=(Literal.__getitem__(tuple(mapping)), ...)
    )
    validators = {}
    constraint = ...
    if collection_name == "fields":
        constraint = Field(..., min_length=len(mapping), max_length=len(mapping))

        def unique_fields(cls, values):
            """Reject duplicate IDs during structured validation so bounded repair can run."""
            if len({value.field_name for value in values}) != len(values):
                raise ValueError("Each requested field ID must appear exactly once")
            return values

        validators["unique_fields"] = field_validator(collection_name)(unique_fields)
    return create_model("Batch" + base.__name__, __base__=base, __validators__=validators,
                        **{collection_name: (list[item], constraint)})


def restore_names(items, mapping, allow_duplicates=False):
    """严格校验短编号与重复项，再原地恢复内部 Word 定位名。

    Args:
        items: 需要恢复编号或汇总的结构化条目。
        mapping: 本批短编号到内部 Word 定位名的映射。
        allow_duplicates: 是否允许同一字段携带多条复核意见。
    """
    seen = set()
    for item in items:
        if item.field_name not in mapping or (item.field_name in seen and not allow_duplicates):
            raise ModelUnavailable("模型返回了无效或重复的字段编号，可仅重试失败批次")
        seen.add(item.field_name)
        item.field_name = mapping[item.field_name]
