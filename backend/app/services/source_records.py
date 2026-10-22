"""Bounded, in-memory import of text and DOCX negotiation records."""

from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from lxml.etree import XMLSyntaxError

from app.config import Settings
from app.documents.word_documents import iter_document_paragraphs
from app.domain.errors import InvalidContractInput


def validate_source_text(text: str, settings: Settings) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").strip()
    if len(normalized) < 10:
        raise InvalidContractInput("请提供至少 10 个字符的协商记录或会议纪要")
    if len(normalized) > settings.max_source_chars:
        raise InvalidContractInput(f"记录超过 {settings.max_source_chars} 字符，请拆分为单笔交易的记录")
    return normalized


def number_source_lines(text: str) -> list[dict]:
    return [{"line_number": number, "text": line} for number, line in enumerate(text.splitlines(), 1)]


def parse_source_file(filename: str, content: bytes, settings: Settings) -> str:
    if not content or len(content) > settings.max_upload_bytes:
        raise InvalidContractInput(f"文件不能为空，且不能超过 {settings.max_upload_bytes // 1024 // 1024} MB")
    extension = Path(filename).suffix.lower()
    if extension in (".txt", ".md"):
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                return validate_source_text(content.decode(encoding), settings)
            except UnicodeDecodeError:
                continue
        raise InvalidContractInput("文本编码无法识别，请另存为 UTF-8")
    if extension == ".docx":
        try:
            with ZipFile(BytesIO(content)) as archive:
                if sum(item.file_size for item in archive.infolist()) > 30 * 1024 * 1024:
                    raise InvalidContractInput("DOCX 解压后过大，请精简记录文件")
            from docx import Document

            document = Document(BytesIO(content))
            text = "\n".join(paragraph.text for paragraph in iter_document_paragraphs(document))
        except InvalidContractInput:
            raise
        except (BadZipFile, KeyError, OSError, XMLSyntaxError, ValueError) as exc:
            raise InvalidContractInput("DOCX 文件损坏或不是有效的 Word 文档") from exc
        return validate_source_text(text, settings)
    raise InvalidContractInput("仅支持 TXT、Markdown 和 DOCX；请将聊天记录或会议纪要导出为这些格式")
