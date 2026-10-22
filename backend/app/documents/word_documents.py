"""Traverse Word paragraphs in XML order, including tables and text boxes."""

from collections.abc import Iterator
from types import SimpleNamespace

from docx.opc.constants import RELATIONSHIP_TYPE
from docx.text.paragraph import Paragraph


def iter_document_paragraphs(document) -> Iterator[Paragraph]:
    """Read each paragraph once; table content remains in its original position."""
    containers = [document]
    # Follow existing relationships, including first/even-page parts. Accessing
    # section.header directly would create missing parts as a read side effect.
    for relationship in document.part.rels.values():
        if (
            relationship.reltype in (RELATIONSHIP_TYPE.HEADER, RELATIONSHIP_TYPE.FOOTER)
            and not relationship.is_external
        ):
            part = relationship.target_part
            containers.append(SimpleNamespace(_element=part.element, part=part))
    seen_parts = set()
    for container in containers:
        element = container._element
        if element in seen_parts:
            continue
        seen_parts.add(element)
        for paragraph_element in element.xpath(".//w:p"):
            yield Paragraph(paragraph_element, container)
