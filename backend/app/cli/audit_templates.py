"""Audit actual DOCX fields without API calls or changing template files."""

import argparse
import json
import re
import sys
from collections import Counter
from io import BytesIO

from docx import Document

from app.config import get_settings
from app.documents.word_documents import iter_document_paragraphs
from app.documents.word_integrity import visual_fingerprint
from app.documents.word_text import paragraph_text
from app.services.contract_templates import ContractTemplateCatalog


def audit_catalog(catalog: ContractTemplateCatalog, *, progress: bool = False) -> dict:
    result = {
        "total": 0,
        "fillable": 0,
        "total_fields": 0,
        "max_fields": 0,
        "generated_slots": 0,
        "verified_roundtrips": 0,
        "visual_review_required": 0,
        "unfillable": [],
        "errors": [],
        "scope": "Text write, DOCX reload and visual/media preservation checks; NOT semantic or visual-content certification.",
    }
    offset = 0
    while True:
        page = catalog.browse_templates(offset=offset, limit=100)
        for template in page["items"]:
            result["total"] += 1
            try:
                details = catalog.describe_template(template["id"])
                fields = details["fields"]
                result["generated_slots"] += details["generated_slots"]
                result["total_fields"] += len(fields)
                result["max_fields"] = max(result["max_fields"], len(fields))
                if details["fillable"]:
                    document, _ = catalog._compiled_document(catalog.get_template(template["id"]))
                    visual_before = visual_fingerprint(document)
                    values = {field["name"]: f"AUDIT_VALUE_{index:06d}" for index, field in enumerate(fields)}
                    filled = set()
                    expected_texts = []
                    for paragraph in iter_document_paragraphs(document):
                        expected = re.sub(
                            r"\{([^{}]+)\}", lambda match: values[match.group(1)], paragraph_text(paragraph)
                        )
                        expected_texts.append(expected)
                        filled.update(catalog._fill_paragraph(paragraph, values))
                        if paragraph_text(paragraph) != expected:
                            raise ValueError("Rendered text does not match expected substitutions")
                    if filled != set(values):
                        raise ValueError("Some detected slots could not be written")
                    stream = BytesIO()
                    document.save(stream)
                    stream.seek(0)
                    reloaded = Document(stream)
                    if [
                        paragraph_text(item) for item in iter_document_paragraphs(reloaded)
                    ] != expected_texts:
                        raise ValueError("DOCX reload changed filled text")
                    if visual_fingerprint(reloaded) != visual_before:
                        raise ValueError("Visual geometry or embedded media changed")
                    result["fillable"] += 1
                    result["verified_roundtrips"] += 1
                    result["visual_review_required"] += int(details["requires_visual_review"])
                else:
                    result["unfillable"].append(
                        {**template, "reasons": details["unsupported_structures"] or ["No detected slots"]}
                    )
            except Exception as error:
                result["errors"].append({"id": template["id"], "name": template["name"], "error": str(error)})
            if progress and result["total"] % 25 == 0:
                print(f"Audited {result['total']}/{page['total']} templates", file=sys.stderr, flush=True)
        offset += len(page["items"])
        if offset >= page["total"]:
            return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Summarize blocked reasons instead of listing all blocked templates",
    )
    parser.add_argument("--progress", action="store_true", help="Print progress to stderr")
    arguments = parser.parse_args()
    settings = get_settings()
    report = audit_catalog(
        ContractTemplateCatalog(settings.resources_dir, settings.generated_dir), progress=arguments.progress
    )
    if arguments.summary:
        blocked = report.pop("unfillable")
        report["blocked_count"] = len(blocked)
        report["blocked_reasons"] = dict(
            Counter(reason for template in blocked for reason in template["reasons"])
        )
    print(json.dumps(report, ensure_ascii=True, indent=2))
    raise SystemExit(1 if report["errors"] else 0)
