"""Typed slot instructions and deterministic guards shared by agents and export."""

import re
from datetime import date

from app.domain.errors import InvalidContractInput


def slot_spec(text: str, start: int, end: int, *, choices=()) -> dict:
    before, after = text[:start], text[end:]
    clause = re.split(r"第[一二三四五六七八九十百]+条|[。；\n]", before)[-1]
    label = re.split(r"[：:]", clause.rstrip(" ：:\t"))[-1].strip()
    label = re.sub(r"\s+", "", label)[-40:] or "待核对空白"
    result = {"display_name": label, "section": "合同正文", "kind": "text", "value_type": "text"}
    if choices:
        following = re.split(r"[。；：:\n]", after)[0]
        result.update(display_name=(label + following)[:70], value_type="choice", choices=list(choices))
    elif re.match(r"\s*[年月日]", after):
        unit = after.lstrip()[0]
        # The nearest year separator determines which side of a date range this is.
        date_prefix = re.split(r"年|月", clause)[0]
        boundary = "结束日期" if re.search(r"至|到", clause) else "开始日期" if "自" in clause else "日期"
        base = re.sub(r"[\s_＿]+", "", date_prefix).strip("：:")[-24:]
        result.update(
            display_name=f"{base or boundary} · {boundary} · {unit}", value_type="date_part", component=unit
        )
    elif re.search(r"[（(]大写[）)]\s*$", before):
        result.update(value_type="money_upper", fixed_unit="元" if after.lstrip().startswith("元") else "")
    return result


def value_issue(spec: dict, value: str) -> str:
    """Reject structurally impossible values even if a model/reviewer accepted them."""
    if not value:
        return ""
    kind = spec.get("value_type", "text")
    if kind == "choice" and value not in spec.get("choices", []):
        return "此位置只能填写选项：" + " / ".join(spec["choices"])
    if kind == "date_part":
        unit = spec["component"]
        if not re.fullmatch(r"[0-9]{1,4}", value):
            return f"此位置只填写{unit}的数字，不含单位、完整日期或日期区间"
        number = int(value)
        lower, upper = (1000, 9999) if unit == "年" else (1, 12) if unit == "月" else (1, 31)
        if not lower <= number <= upper:
            return f"{unit}必须在 {lower}–{upper} 范围内"
    if kind == "money_upper" and (
        re.search(r"[0-9]", value) or not re.search(r"[零壹贰叁肆伍陆柒捌玖拾佰仟万亿]", value)
    ):
        return "此位置填写中文大写金额，不含重复的金额标签"
    if kind == "money_upper" and spec.get("fixed_unit") and ("元" in value or value.endswith("整")):
        return "模板右侧已含元，本格只填叁仟等大写数额，不重复填写元或整"
    if re.search(r"\{[^{}]+\}|\[当前填写处\]", value):
        return "填写内容包含内部字段标记"
    return ""


def validate_slot_values(fields: list[dict], values: dict[str, str]) -> None:
    dates = {}
    for field in fields:
        issue = value_issue(field, values.get(field["name"], ""))
        if issue:
            raise InvalidContractInput(f"{field.get('display_name') or field['name']}：{issue}")
        if field.get("date_group") and values.get(field["name"]):
            dates.setdefault(field["date_group"], {})[field["component"]] = int(values[field["name"]])
    for parts in dates.values():
        if all(unit in parts for unit in "年月日"):
            try:
                date(*(parts[unit] for unit in "年月日"))
            except ValueError as error:
                raise InvalidContractInput("填写的年月日不是有效日历日期，请核对") from error
