"""Check repository renames without discarding data or cataloguing backups."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from docx import Document

from app.config import default_database_path
from app.services.contract_templates import ContractTemplateCatalog


class ProjectLayoutTests(TestCase):
    def test_database_name_preserves_existing_data_and_supports_clean_installs(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data"
            data.mkdir()
            current = data / "contractweaver.db"
            previous = data / "lawreasoner.db"
            with patch("app.config.BASE_DIR", root):
                self.assertEqual(default_database_path(), current)
                previous.touch()
                self.assertEqual(default_database_path(), previous)
                current.touch()
                self.assertEqual(default_database_path(), current)

    def test_catalog_discovers_originals_and_keywords_but_not_legacy_backups(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            originals = root / "templates" / "Ministerial"
            keywords = originals / "关键词"
            backup = root / "legacy" / "placeholder-templates" / "Ministerial"
            keywords.mkdir(parents=True)
            backup.mkdir(parents=True)
            document = Document()
            document.add_paragraph("甲方____")
            document.save(originals / "合同原件.docx")
            document.save(backup / "不应出现的旧转换合同.docx")
            (keywords / "合同原件.txt").write_text("精密设备采购", encoding="utf-8")
            catalog = ContractTemplateCatalog(root, root / "generated")
            items = catalog.list_templates()
            self.assertEqual([item["name"] for item in items], ["合同原件"])
            results = catalog.search_templates("精密设备采购")
            self.assertEqual(results[0]["id"], items[0]["id"])
            self.assertTrue(catalog.describe_template(items[0]["id"])["fillable"])
