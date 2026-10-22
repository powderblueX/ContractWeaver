"""Synchronize equal Word compatibility branches instead of double-filling them."""

from dataclasses import dataclass

from docx.oxml.ns import qn

from app.documents.word_documents import iter_document_paragraphs
from app.documents.word_text import paragraph_text

ALTERNATE_TAG = "{http://schemas.openxmlformats.org/markup-compatibility/2006}AlternateContent"


@dataclass(frozen=True)
class CompatibilityMap:
    mirrors: dict
    alias_elements: frozenset
    blockers: tuple[str, ...]


def inspect_compatibility(paragraphs: list) -> CompatibilityMap:
    by_element = {paragraph._p: paragraph for paragraph in paragraphs}
    roots = {element.getroottree().getroot() for element in by_element}
    mirrors, aliases, blockers = {}, set(), []
    for root in roots:
        for alternate in root.iter(ALTERNATE_TAG):
            branches = [branch for branch in alternate if list(branch.iter(qn("w:txbxContent")))]
            if len(branches) < 2:
                continue
            if any(list(branch.iter(ALTERNATE_TAG)) for branch in branches):
                blockers.append("嵌套文本框兼容分支尚未支持")
                continue
            groups = [
                [by_element[element] for element in branch.iter(qn("w:p")) if element in by_element]
                for branch in branches
            ]
            texts = [[paragraph_text(paragraph) for paragraph in group] for group in groups]
            if not groups[0] or any(value != texts[0] for value in texts[1:]):
                blockers.append("文本框兼容分支内容不一致，无法安全同步")
                continue
            for index, paragraph in enumerate(groups[0]):
                copies = tuple(group[index] for group in groups[1:])
                mirrors[paragraph._p] = copies
                aliases.update(copy._p for copy in copies)
    return CompatibilityMap(mirrors, frozenset(aliases), tuple(sorted(set(blockers))))


def iter_visible_document_paragraphs(document):
    """Preview one logical copy; actual rendering still writes all mirrored parts."""
    paragraphs = list(iter_document_paragraphs(document))
    mapping = inspect_compatibility(paragraphs)
    return (paragraph for paragraph in paragraphs if paragraph._p not in mapping.alias_elements)
