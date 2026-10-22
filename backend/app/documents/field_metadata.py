"""Human labels/grouping are presentation metadata, never Word locator changes."""

import re


def field_metadata(name, context):
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
