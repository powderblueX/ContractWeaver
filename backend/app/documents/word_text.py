"""Edit Word text leaves, never resetting runs that may contain graphics."""

from bisect import bisect_right
from dataclasses import dataclass

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from app.domain.errors import InvalidContractInput

TEXT_TAG = qn("w:t")
SKIP_TAGS = {qn(name) for name in ("w:p", "w:pPr", "w:rPr", "w:drawing", "w:pict", "w:object")}


@dataclass(frozen=True)
class TextAtom:
    """保留可见文字及其原 XML 叶节点的位置单元。"""

    element: object
    value: str


def paragraph_atoms(paragraph) -> list[TextAtom]:
    """Nested text-box paragraphs are visited separately, not duplicated here."""
    atoms = []

    def visit(parent):
        """递归读取文字叶节点，跳过会重复遍历的段落和视觉对象。

        Args:
            parent: 当前 XML 遍历的父节点。
        """
        for element in parent:
            if element.tag in SKIP_TAGS:
                continue
            if element.tag == TEXT_TAG:
                atoms.append(TextAtom(element, element.text or ""))
            elif element.tag == qn("w:tab"):
                atoms.append(TextAtom(element, "\t"))
            elif element.tag in (qn("w:br"), qn("w:cr")):
                if element.get(qn("w:type"), "textWrapping") == "textWrapping":
                    atoms.append(TextAtom(element, "\n"))
            else:
                visit(element)

    visit(paragraph._p)
    return atoms


def paragraph_text(paragraph) -> str:
    """按可见 XML 文字原子拼接段落，保留正文中的实际制表和换行。

    Args:
        paragraph: 保留原 XML 定位的 Word 段落。
    """
    return "".join(atom.value for atom in paragraph_atoms(paragraph))


def replace_text_ranges(paragraph, replacements: list[tuple[int, int, str]]) -> None:
    """Apply non-overlapping ranges using original offsets and preserve XML.

    Only w:t values change; drawings, relationship IDs, run styles and hyperlinks
    are untouched. Crossing layout tabs or line breaks fails closed.
    """
    atoms = [atom for atom in paragraph_atoms(paragraph) if atom.value]
    texts = [atom.value for atom in atoms]
    offsets = []
    length = 0
    for text in texts:
        offsets.append(length)
        length += len(text)
    previous_start = length + 1
    append_value = ""
    for start, end, value in sorted(replacements, reverse=True):
        if not 0 <= start <= end <= length or end > previous_start:
            raise InvalidContractInput("模板填写位置无效或发生重叠")
        previous_start = start
        if start == length:
            if atoms and atoms[-1].element.tag == TEXT_TAG:
                texts[-1] += value
            else:
                append_value = value + append_value
            continue
        first = bisect_right(offsets, start) - 1
        last = first if start == end else bisect_right(offsets, end - 1) - 1
        if start == end and atoms[first].element.tag != TEXT_TAG:
            inserted = OxmlElement("w:t")
            inserted.text = value
            atoms[first].element.addprevious(inserted)
            continue
        if any(atom.element.tag != TEXT_TAG for atom in atoms[first : last + 1]):
            raise InvalidContractInput("填写字段跨越换行或制表符，请维护模板后使用")
        left, right = start - offsets[first], end - offsets[last]
        prefix, suffix = texts[first][:left], texts[last][right:]
        if first == last:
            texts[first] = prefix + value + suffix
        else:
            texts[first] = prefix + value
            for index in range(first + 1, last):
                texts[index] = ""
            texts[last] = suffix
    for atom, text in zip(atoms, texts):
        if atom.value != text:
            atom.element.text = text
            if text and (text[0].isspace() or text[-1].isspace()):
                atom.element.set(qn("xml:space"), "preserve")
    if append_value:
        paragraph.add_run(append_value)
