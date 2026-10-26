"""Container bootstrap never starts the HTTP server before dropping privileges."""

import os
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from app.container_entrypoint import main


class ContainerEntrypointTests(TestCase):
    """测试夹具或替身：ContainerEntrypointTests，用于隔离验证本模块行为。"""

    def test_private_secret_copy_and_privilege_drop_before_exec(self):
        """Verify private secret copy and privilege drop before exec."""
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)
            source = root / "source.env"
            source.write_text("LAW_LLM_API_KEY=synthetic-test-only\n", encoding="utf-8")
            descriptor, filename = tempfile.mkstemp(dir=root)
            stack.enter_context(patch.dict(os.environ, {"LAW_ENV_FILE": str(source)}))
            stack.enter_context(patch("sys.argv", ["entrypoint", "python", "-m", "uvicorn"]))
            stack.enter_context(
                patch("app.container_entrypoint.tempfile.mkstemp", return_value=(descriptor, filename))
            )
            calls = []
            for name in ("chown", "setgroups", "setgid", "setuid", "execvp"):
                stack.enter_context(
                    patch.object(
                        os, name, side_effect=lambda *args, name=name: calls.append((name, args)), create=True
                    )
                )
            main()
            self.assertEqual(Path(filename).read_bytes(), source.read_bytes())
            self.assertEqual(os.environ["LAW_ENV_FILE"], filename)
            self.assertEqual(
                [name for name, _ in calls], ["chown", "setgroups", "setgid", "setuid", "execvp"]
            )
            self.assertEqual(calls[3][1], (10001,))
            self.assertEqual(calls[4][1], ("python", ["python", "-m", "uvicorn"]))

    def test_missing_secret_stops_before_server_start(self):
        """Verify missing secret stops before server start."""
        with (
            patch.dict(os.environ, {"LAW_ENV_FILE": "/missing-contractweaver-secret"}),
            patch("sys.argv", ["entrypoint", "python"]),
            patch("os.execvp") as execute,
        ):
            with self.assertRaises(SystemExit):
                main()
            execute.assert_not_called()
