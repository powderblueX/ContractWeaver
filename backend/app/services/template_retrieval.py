"""Small local BM25 indexes and rank fusion over template metadata.

Chinese character bigrams avoid a mandatory tokenizer/model dependency. This
retrieves candidates; it does not certify contract applicability or optimality.
"""

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalPolicy:
    candidate_pool: int = 30
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    rrf_constant: int = 60
    title_weight: float = 2.0
    keyword_weight: float = 1.0
    vector_weight: float = 1.0
    exact_weight: float = 2.0


def normalize_title(text: str) -> str:
    """Ignore typography, not business meaning or version identifiers."""
    return re.sub(r"[\s《》〈〉\"'“”]", "", unicodedata.normalize("NFKC", text).casefold())


def title_aliases(name: str) -> set[str]:
    """Use the full catalog title and its literal contract-name portion."""
    aliases = {normalize_title(name)}
    quoted = re.search(r"《([^》]+)》", name)
    base = quoted.group(1) if quoted else re.split(r"[（(]", name, maxsplit=1)[0]
    if len(base) >= 4 and "合同" in base:
        aliases.add(normalize_title(base))
    return aliases


def explicit_source_titles(source: str, catalog_names: list[str]) -> set[str]:
    """Rescue literal positive requests even when the analysis model omits them.

    This deliberately does not infer synonyms or resolve conversation history.
    Negated/question clauses do not qualify; final selection is always human.
    """
    requested = set()
    clauses = re.findall(r"[^，,。；;！？!?\n]+[！？!?]?", source)
    aliases = {alias for name in catalog_names for alias in title_aliases(name)}
    for clause in clauses:
        normalized = normalize_title(clause)
        if clause.endswith(("?", "？")):
            continue
        for alias in aliases:
            position = normalized.find(alias)
            if position < 0:
                continue
            prefix = normalized[max(0, position - 24) : position]
            if re.search(
                r"不需要|无需|不要|不用|不采用|不使用|不签|不选|取消|否决|暂不|不再|并非|不是", prefix
            ):
                continue
            if re.search(r"需要|选用|选择|采用|使用|签订|起草|生成|填写|准备|请提供|我要", prefix):
                requested.add(alias)
    return requested


def tokenize(text: str) -> list[str]:
    tokens = []
    for segment in re.findall(r"[\u4e00-\u9fff]+|[a-z0-9]+", text.casefold()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", segment):
            if len(segment) > 1:
                tokens.extend(segment[index : index + 2] for index in range(len(segment) - 1))
            else:
                tokens.append(segment)
        else:
            tokens.append(segment)
    return tokens


def bm25_scores(query: str, documents: list[str], policy: RetrievalPolicy) -> list[float]:
    counters = [Counter(tokenize(document)) for document in documents]
    lengths = [sum(counter.values()) for counter in counters]
    average = sum(lengths) / max(1, len(lengths)) or 1.0
    frequencies = Counter(term for counter in counters for term in counter)
    query_terms = set(tokenize(query))
    scores = []
    for counter, length in zip(counters, lengths):
        score = 0.0
        for term in query_terms & counter.keys():
            inverse_frequency = math.log(
                1 + (len(documents) - frequencies[term] + 0.5) / (frequencies[term] + 0.5)
            )
            frequency = counter[term]
            denominator = frequency + policy.bm25_k1 * (1 - policy.bm25_b + policy.bm25_b * length / average)
            score += inverse_frequency * frequency * (policy.bm25_k1 + 1) / denominator
        scores.append(score)
    return scores


def rank_metadata(
    query: str, records: list[dict], vector_ranks: dict[str, float], policy: RetrievalPolicy
) -> list[dict]:
    """Fuse ranks, not incomparable raw BM25 and vector score magnitudes."""
    if not records:
        return []
    indexes = {record["id"]: index for index, record in enumerate(records)}
    title = bm25_scores(query, [item["name"] for item in records], policy)
    keywords = bm25_scores(query, [item["keywords"] for item in records], policy)
    rankings = []
    for label, scores, weight in (
        ("title_bm25", title, policy.title_weight),
        ("keyword_bm25", keywords, policy.keyword_weight),
    ):
        ranking = sorted(
            (index for index, score in enumerate(scores) if score > 0),
            key=lambda index: (-scores[index], records[index]["name"], records[index]["id"]),
        )
        if ranking:
            rankings.append((label, ranking, weight))
    exact = [
        index
        for index, item in enumerate(records)
        if query.strip().casefold() in item["name"].casefold() or item["name"].casefold() in query.casefold()
    ]
    if exact:
        rankings.append(
            (
                "exact_title",
                sorted(
                    exact,
                    key=lambda index: (abs(len(records[index]["name"]) - len(query)), records[index]["id"]),
                ),
                policy.exact_weight,
            )
        )
    vector = sorted(
        (key for key in vector_ranks if key in indexes), key=lambda key: (-vector_ranks[key], key)
    )
    if vector:
        rankings.append(("vector", [indexes[key] for key in vector], policy.vector_weight))
    fused, sources = Counter(), {}
    for label, ranking, weight in rankings:
        for rank, index in enumerate(ranking, 1):
            fused[index] += weight / (policy.rrf_constant + rank)
            sources.setdefault(index, []).append(label)
    maximum = sum(weight / (policy.rrf_constant + 1) for _, _, weight in rankings) or 1
    return [
        {"id": records[index]["id"], "score": round(fused[index] / maximum, 6), "sources": sources[index]}
        for index in sorted(
            fused, key=lambda index: (-fused[index], records[index]["name"], records[index]["id"])
        )
    ]
