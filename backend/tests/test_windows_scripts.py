"""Windows shutdown helpers identify project processes, not arbitrary Node/Python."""

import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts" / "windows-project-processes.ps1"


def quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "Windows PowerShell required")
class WindowsScriptTests(TestCase):
    def run_script(self, body: str):
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "$ErrorActionPreference='Stop'; . " + quote(str(HELPER)) + "; " + body,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_process_scope_and_child_discovery_do_not_match_other_projects(self):
        body = r"""
        $root = 'C:\Example ContractWeaver'
        $time = [datetime]'2026-10-21T10:00:00'
        function New-FakeProcess($id, $parent, $name, $exe, $command, $offset) {
            [pscustomobject]@{ProcessId=$id;ParentProcessId=$parent;Name=$name;ExecutablePath=$exe;CommandLine=$command;CreationDate=$time.AddSeconds($offset)}
        }
        $script:fakeProcesses = @(
            (New-FakeProcess 45001 1 'python.exe' "$root\backend\.venv\Scripts\python.exe" 'python -m uvicorn app.main:app' 0),
            (New-FakeProcess 45002 45001 'python.exe' 'C:\Python\python.exe' 'python -m uvicorn app.main:app' 1),
            (New-FakeProcess 45003 1 'node.exe' 'C:\node.exe' ('node "' + $root + '\frontend\node_modules\vite\bin\vite.js"') 0),
            (New-FakeProcess 45004 1 'node.exe' 'C:\node.exe' 'node C:\OtherProject\server.js' 0),
            (New-FakeProcess 45005 1 'python.exe' 'C:\OtherProject\.venv\python.exe' 'python -m uvicorn app.main:app' 0),
            (New-FakeProcess 45006 1 'powershell.exe' 'C:\powershell.exe' ('powershell -NoProfile -File "' + $root + '\scripts\start-backend.ps1" -Port 8000') 0),
            (New-FakeProcess 45007 1 'powershell.exe' 'C:\powershell.exe' ('powershell -Command echo -File "' + $root + '\scripts\start-backend.ps1"') 0),
            (New-FakeProcess 45008 1 'cmd.exe' 'C:\cmd.exe' ('cmd /c ""' + $root + '\scripts\start-frontend.bat""') 0)
        )
        function Get-CimInstance { param($ClassName, $ErrorAction) $script:fakeProcesses }
        $ids = @(Get-ContractWeaverProcessSnapshot -ProjectRoot $root | ForEach-Object { $_.ProcessId } | Sort-Object)
        if (($ids -join ',') -ne '45001,45002,45003,45006,45008') { throw ('Unexpected process scope: ' + ($ids -join ',')) }
        """
        self.run_script(body)

    def test_cleanup_is_bounded_and_preserves_configuration_and_data(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "Project With Spaces"
            cache = root / "frontend" / ".npm-cache"
            cache.mkdir(parents=True)
            (cache / "test.log").write_text("synthetic cache", encoding="utf-8")
            (root / "backend" / "data").mkdir(parents=True)
            (root / "backend" / ".env").write_text("synthetic config", encoding="utf-8")
            sentinel = root / "backend" / "data" / "keep.db"
            sentinel.write_text("synthetic data", encoding="utf-8")
            body = (
                "$root = "
                + quote(str(root))
                + "; "
                + r"""
                Remove-ContractWeaverGeneratedDirectory -ProjectRoot $root -RelativePath 'frontend/.npm-cache'
                $refused = $false
                try { Remove-ContractWeaverGeneratedDirectory -ProjectRoot $root -RelativePath '../outside' } catch { $refused = $true }
                if (-not $refused) { throw 'Escaping target was not refused' }
            """
            )
            self.run_script(body)
            self.assertFalse(cache.exists())
            self.assertTrue((root / "backend" / ".env").is_file())
            self.assertTrue(sentinel.is_file())
