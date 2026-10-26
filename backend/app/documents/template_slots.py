"""Compile original Word blanks into unique, human-reviewed structural fields."""

import re
from dataclasses import dataclass, field

from docx.oxml.ns import qn
from docx.text.run import Run

from app.documents.slot_constraints import slot_spec
from app.documents.template_safety import inspect_template_safety
from app.documents.word_compatibility import inspect_compatibility
from app.documents.word_documents import iter_document_paragraphs
from app.documents.word_text import TEXT_TAG, paragraph_atoms, paragraph_text, replace_text_ranges

# 修改识别语义时必须升级此值，使旧任务不能继续用过期位置映射写回原件。
SLOT_ENGINE_VERSION = "typed-text-slots-20261022"
BLANK_PATTERN = re.compile(r"[_＿﹍﹎]{2,}|[…⋯]{2,}|(?<=\S)[ \u3000\u00a0]{2,}(?=\S)")
MARKER_PATTERN = re.compile(r"\{[^{}]+\}")


@dataclass(frozen=True)
class SlotCompilation:
    """保存内存编译产生的位置、原始空白、类型约束和安全结论。"""

    generated_slots: int
    unsupported: tuple[str, ...]
    original_blanks: dict[str, str]
    warnings: tuple[str, ...] = ()
    requires_visual_review: bool = False
    field_specs: dict[str, dict] = field(default_factory=dict)


def compile_template_slots(document) -> SlotCompilation:
    """Detect candidates without flattening runs, text boxes or visual objects."""
    paragraphs = list(iter_document_paragraphs(document))
    compatibility = inspect_compatibility(paragraphs)
    safety = inspect_template_safety(document, paragraphs, compatibility)
    unsupported = list(safety.blockers)
    existing_names = {
        match.group(0)[1:-1]
        for paragraph in paragraphs
        for match in MARKER_PATTERN.finditer(paragraph_text(paragraph))
    }
    generated = 0
    original_blanks = {}
    field_specs = {}

    def unique_name(name):
        """为当前原件生成不与已有字段重名的内部定位标识。

        Args:
            name: 字段、步骤或模板的受控名称。
        """
        while name in existing_names:
            name += "·"
        existing_names.add(name)
        return name

    for paragraph_number, paragraph in enumerate(paragraphs, 1):
        if paragraph._p in compatibility.alias_elements:
            continue
        atoms = paragraph_atoms(paragraph)
        text = "".join(atom.value for atom in atoms)
        markers = [(match.start(), match.end()) for match in MARKER_PATTERN.finditer(text)]
        if any("\n" in match.group() or "\t" in match.group() for match in MARKER_PATTERN.finditer(text)):
            unsupported.append("填写标记跨越换行或制表符")
        spans = [(match.start(), match.end()) for match in BLANK_PATTERN.finditer(text)]
        cursor = 0
        underlined_spans = set()
        for atom in atoms:
            run = atom.element.getparent()
            if atom.element.tag == TEXT_TAG and run.tag == qn("w:r"):
                if Run(run, paragraph).underline and atom.value and not atom.value.strip():
                    spans.append((cursor, cursor + len(atom.value)))
                    underlined_spans.add((cursor, cursor + len(atom.value)))
            # A real underlined tab represents a blank too. Insert before it;
            # do not confuse paragraph tab-stop definitions with actual tabs.
            if atom.element.tag == qn("w:tab") and run.tag == qn("w:r") and Run(run, paragraph).underline:
                spans.append((cursor, cursor))
            cursor += len(atom.value)

        cell = paragraph._p.getparent()
        if cell.tag == qn("w:tc"):
            merges = cell.xpath("./w:tcPr/w:vMerge | ./w:tcPr/w:hMerge")
            if any(merge.get(qn("w:val"), "continue") == "continue" for merge in merges):
                if "".join(cell.xpath(".//w:t/text()")).strip():
                    unsupported.append("合并单元格延续区存在文字")
                continue
        empty_container = None
        label = ""
        if cell.tag == qn("w:tc") and not "".join(cell.xpath(".//w:t/text()")).strip():
            if paragraph._p is cell.xpath("./w:p")[0] and not cell.xpath(".//w:drawing | .//w:pict"):
                empty_container, label = cell, "表格空白"
        text_boxes = paragraph._p.xpath("ancestor::w:txbxContent")
        if empty_container is None and text_boxes:
            box = text_boxes[-1]
            if not "".join(node.text or "" for node in box.iter(qn("w:t"))).strip():
                box_paragraphs = list(box.iter(qn("w:p")))
                if (
                    box_paragraphs
                    and paragraph._p is box_paragraphs[0]
                    and not list(box.iter(qn("w:drawing")))
                    and not list(box.iter(qn("w:pict")))
                ):
                    empty_container, label = box, "文本框空白"
        if empty_container is not None:
            name = unique_name(f"{label}·位置{paragraph_number}")
            replace_text_ranges(paragraph, [(len(text), len(text), "{" + name + "}")])
            for mirror in compatibility.mirrors.get(paragraph._p, ()):
                replace_text_ranges(mirror, [(len(text), len(text), "{" + name + "}")])
            original_blanks[name] = ""
            generated += 1
            continue

        # Adjacent labels such as 出卖人：签订地点： have no explicit whitespace.
        # Decorative headings remain candidates, not silently invented facts.
        for match in re.finditer(r"[：:][ \u3000\u00a0]*", text):
            start, end = match.start() + 1, match.end()
            tail = text[end:]
            if re.search(r"下列第[^。；\n]*种[^。；\n]*[：:]$", text[:end]):
                continue
            adjacent_label = re.match(r"[^\s：:]{1,16}[：:]", tail)
            if not tail.startswith(("{", "_", "＿")) and (
                not tail or tail[0].isspace() or end > start or adjacent_label
            ):
                spans.append((start, end))
        choices = {}
        for match in re.finditer(
            r"[（(][ \u3000\u00a0]*((?:是[ \u3000\u00a0]*[/／][ \u3000\u00a0]*否)|(?:有[ \u3000\u00a0]*[/／][ \u3000\u00a0]*无))[ \u3000\u00a0]*[）)]",
            text,
        ):
            start, end = match.span(1)
            spans.append((start, end))
            choices[(start, end)] = re.split(r"\s*[/／]\s*", match.group(1))
        merged = []
        for start, end in sorted(set(spans)):
            if any(left <= start < right or start < right and end > left for left, right in markers):
                continue
            # Clause-number spacing is never an input, regardless of run style.
            if re.search(r"第[一二三四五六七八九十百]+条\s*$", text[:start]):
                continue
            if (
                start < end
                and (start, end) not in underlined_spans
                and text[start:end].isspace()
                and re.search(r"[\u4e00-\u9fff]$", text[:start])
                and re.match(r"[\u4e00-\u9fff]", text[end:])
                and text[end] not in "年月日元吨台件箱米份种"
            ):
                continue
            # One logical blank may contain several underlined runs plus tabs.
            # Keep the first editable range and absorb further whitespace-only
            # candidates without creating a second field across the tab.
            if (
                merged
                and text[merged[-1][1] : end].isspace()
                and text[merged[-1][0] : end].isspace()
                and not any(separator in text[merged[-1][0] : end] for separator in ("\n", "\r"))
            ):
                if "\t" not in text[merged[-1][0] : end]:
                    merged[-1] = (merged[-1][0], end)
                continue
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        replacements = []
        date_number = 0
        for slot_number, (start, end) in enumerate(merged, 1):
            label = re.sub(r"[{}\s_＿]+", "", text[max(0, start - 24) : start])[-20:] or "待核对空白"
            name = unique_name(f"{label}·位置{paragraph_number}-{slot_number}")
            field_specs[name] = slot_spec(text, start, end, choices=choices.get((start, end), ()))
            if field_specs[name].get("value_type") == "date_part":
                if field_specs[name]["component"] == "年":
                    date_number += 1
                field_specs[name]["date_group"] = f"paragraph-{paragraph_number}-date-{date_number}"
            original_blanks[name] = text[start:end]
            replacements.append((start, end, "{" + name + "}"))
            generated += 1
        replace_text_ranges(paragraph, replacements)
        for mirror in compatibility.mirrors.get(paragraph._p, ()):
            replace_text_ranges(mirror, replacements)
    return SlotCompilation(
        generated,
        tuple(sorted(set(unsupported))),
        original_blanks,
        safety.warnings,
        safety.requires_visual_review,
        field_specs,
    )
