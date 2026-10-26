"""Fingerprint visual geometry and embedded payloads outside editable text boxes."""

from copy import deepcopy
from hashlib import sha256

from docx.oxml.ns import qn
from lxml import etree

from app.documents.word_documents import iter_document_paragraphs


def visual_fingerprint(document) -> tuple:
    """对图形框体和媒体生成指纹，允许修改文本框文字但不允许破坏图形结构。

    Args:
        document: 内存中的 Word 文档对象，不能据此改动原件。
    """
    roots = [document.element]
    for paragraph in iter_document_paragraphs(document):
        root = paragraph._p.getroottree().getroot()
        if root not in roots:
            roots.append(root)
    graphics = []
    for root in roots:
        for element in root.xpath(".//w:drawing | .//w:pict | .//w:object"):
            snapshot = deepcopy(element)
            # Text-box content is editable. Outer geometry and every nested
            # visual object are checked independently by the traversal above.
            for content in snapshot.iter(qn("w:txbxContent")):
                for child in list(content):
                    content.remove(child)
                content.text = None
            graphics.append(etree.tostring(snapshot, method="c14n"))
    payloads = tuple(
        sorted(
            (str(part.partname), sha256(part.blob).hexdigest())
            for part in document.part.package.parts
            if any(segment in str(part.partname) for segment in ("/media/", "/embeddings/", "/charts/"))
        )
    )
    return tuple(graphics), payloads
