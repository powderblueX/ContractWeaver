"""Read-only Civil Code article lookup and search for grounded answers."""

from functools import lru_cache
from pathlib import Path
import json
import re


class CivilCode:
    def __init__(self, data_path: Path):
        self.data_path = data_path

    @lru_cache(maxsize=1)
    def articles(self) -> list[str]:
        data = json.loads(self.data_path.read_text(encoding="utf-8"))
        return [str(item["output"]) for item in data]

    def lookup(self, article: int) -> dict:
        items = self.articles()
        if article < 1 or article > len(items):
            raise ValueError("法条编号超出本地民法典范围")
        return {"article": article, "text": items[article - 1], "source": "本地《中华人民共和国民法典》"}

    def search(self, query: str, limit: int = 5) -> list[dict]:
        terms = [part for part in re.split(r"[\s，。；、]+", query.strip()) if len(part) >= 2]
        if not terms:
            raise ValueError("请提供至少两个字的检索词")
        scored = []
        for number, content in enumerate(self.articles(), 1):
            score = sum(content.count(term) for term in terms)
            if score:
                scored.append((score, number))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [self.lookup(number) for _, number in scored[:max(1, min(limit, 10))]]
