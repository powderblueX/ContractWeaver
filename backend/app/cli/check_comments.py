"""检查 Python 模块、类和具名函数的说明覆盖；不据此判断注释语义正确。"""

import ast
import json
from pathlib import Path


def inspect_paths(paths):
    """返回指定源文件的文档覆盖统计和缺失位置。

    Args:
        paths: 受控检查目录下的 Python 路径集合，不读取配置或用户数据库。

    Returns:
        含文件、类、函数数量及缺失位置的字典。检查只读，不修改代码。
    """
    result = {"files": 0, "classes": 0, "functions": 0, "missing": []}
    for path in sorted(paths):
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path))
        result["files"] += 1
        if not ast.get_docstring(tree):
            result["missing"].append(f"{path}:1 module")
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                result["classes" if isinstance(node, ast.ClassDef) else "functions"] += 1
                if not ast.get_docstring(node):
                    result["missing"].append(f"{path}:{node.lineno} {node.name}")
    return result


def main():
    """只读检查业务与测试源文件，并通过退出码报告覆盖缺口。"""
    backend = Path(__file__).resolve().parents[2]
    result = inspect_paths([*backend.joinpath("app").rglob("*.py"), *backend.joinpath("tests").rglob("*.py")])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
