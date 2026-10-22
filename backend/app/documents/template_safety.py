"""Separate unsupported editable structures from preserved visual content."""

import re
from dataclasses import dataclass

from docx.oxml import parse_xml
from docx.oxml.ns import qn

from app.documents.word_compatibility import inspect_compatibility


@dataclass(frozen=True)
class TemplateSafety:
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    requires_visual_review: bool


def inspect_template_safety(document, paragraphs: list, compatibility=None) -> TemplateSafety:
    blockers, warnings = [], []
    visual_review = False
    compatibility = compatibility or inspect_compatibility(paragraphs)
    blockers.extend(compatibility.blockers)
    for part in document.part.package.parts:
        if part.partname.endswith(("/footnotes.xml", "/endnotes.xml")):
            if any(int(note.get(qn("w:id"), "0")) > 0 for note in parse_xml(part.blob)):
                blockers.append("脚注或尾注")
    roots = {document.element, *(paragraph._p.getroottree().getroot() for paragraph in paragraphs)}
    for elements in roots:
        for query, label in (
            (".//w:object", "嵌入对象"),
            (".//w:altChunk", "外部导入内容"),
            (".//w:sdt", "内容控件"),
            (".//w:ffData", "旧版表单域"),
            (".//w:ins | .//w:del", "未接受的修订"),
        ):
            if elements.xpath(query):
                blockers.append(label)
        instructions = elements.xpath(".//w:instrText/text() | .//w:fldSimple/@w:instr")
        if re.search(
            r"\b(?:MERGEFIELD|FORMTEXT|FORMCHECKBOX|FORMDROPDOWN|FILLIN|ASK)\b", " ".join(instructions), re.I
        ):
            blockers.append("邮件合并或交互式填写域")
        for graphic in elements.xpath(".//w:drawing | .//w:pict"):
            if list(graphic.iter(qn("w:txbxContent"))):
                warnings.append("Word 文本框已纳入字段扫描，框体保留；请核对长文本是否溢出")
                # A text box may also contain an image; still require inspection.
                if not any(
                    node.tag.endswith("}blip") or node.tag.endswith("}imagedata") for node in graphic.iter()
                ):
                    continue
            pure_line_tags = {
                "{urn:schemas-microsoft-com:vml}line",
                "{urn:schemas-microsoft-com:vml}group",
                "{urn:schemas-microsoft-com:vml}stroke",
                "{urn:schemas-microsoft-com:office:word}wrap",
                "{urn:schemas-microsoft-com:office:office}lock",
            }
            descendants = list(graphic.iterdescendants())
            if descendants and all(node.tag in pure_line_tags for node in descendants):
                continue
            visual_review = True
    if visual_review:
        warnings.append(
            "图片、图形或图表将原样保留，不执行 OCR 或图中填写；导出前必须另行确认这些区域不需要自动填写"
        )
    return TemplateSafety(tuple(sorted(set(blockers))), tuple(sorted(set(warnings))), visual_review)
