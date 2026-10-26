"""Human labels/grouping are presentation metadata, never Word locator changes."""

import re


def field_metadata(name, context):
    """结合表格和邻近文字，为内部位置生成可读含义及展示分类。

    Args:
        name: 字段、步骤或模板的受控名称。
        context: 当前填写处附近的模板文字。
    """
    label = re.sub(r"·位置.*$", "", name).strip()
    label = re.split(r"第[一二三四五六七八九十百]+条", label)[-1].strip(" ：:，,。") or "条款间空白"
    if "：" in label or ":" in label:
        label = re.split(r"[：:]", label.rstrip("：:"))[-1]
    layout = bool(re.fullmatch(r"第[一二三四五六七八九十百]+条|条款间空白|（?注|年|月", label))
    return {
        "display_name": label or "待核对空白",
        "section": "排版与其他候选" if layout else "合同正文",
        "kind": "layout" if layout else "text",
    }
