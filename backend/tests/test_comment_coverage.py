"""验证注释覆盖检查器能够识别模块、类和函数缺口。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from app.cli.check_comments import inspect_paths


class CommentCoverageTests(TestCase):
    """使用临时文本验证检测器，并检查项目受维护 Python 代码的覆盖。"""

    def test_project_python_sources_have_module_class_and_function_docs(self):
        """Verify documented production and test sources without accessing user data."""
        backend = Path(__file__).resolve().parents[1]
        result = inspect_paths(
            [*backend.joinpath("app").rglob("*.py"), *backend.joinpath("tests").rglob("*.py")]
        )
        self.assertEqual(result["missing"], [])

    def test_plain_comments_do_not_replace_function_docstrings(self):
        """Verify a hash comment does not count as a Python function docstring."""
        with TemporaryDirectory() as temporary:
            # 此处只创建隔离测试夹具；不改动仓库源文件。
            sample = Path(temporary) / "sample.py"
            sample.write_text("# comment\ndef missing():\n    pass\n", encoding="utf-8")
            result = inspect_paths([sample])
        self.assertEqual(len(result["missing"]), 2)
