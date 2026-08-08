"""In-house BM25 scorer (Robertson–Sparck Jones), dependency-free and mypy-strict clean."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_TOKEN = re.compile(r"[A-Za-z0-9]+")


@dataclass(frozen=True)
class ScoredPassage:
    index: int
    passage: str
    score: float


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN.findall(text)]


@dataclass
class Bm25Scorer:
    passages: list[str]
    k1: float = 1.2
    b: float = 0.75

    def __post_init__(self) -> None:
        self._docs: list[list[str]] = [tokenize(p) for p in self.passages]
        self._doc_lengths = [len(doc) for doc in self._docs]
        self._avgdl = sum(self._doc_lengths) / len(self._docs) if self._docs else 0.0
        self._df: dict[str, int] = {}
        for doc in self._docs:
            for term in set(doc):
                self._df[term] = self._df.get(term, 0) + 1

    def _idf(self, term: str) -> float:
        n = len(self._docs)
        df = self._df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def retrieve(self, query: str, k: int = 3) -> list[ScoredPassage]:
        terms = tokenize(query)
        scores: list[float] = []
        for dl, doc in zip(self._doc_lengths, self._docs, strict=False):
            freq = {term: doc.count(term) for term in set(terms)}
            score = 0.0
            for term in terms:
                tf = freq[term]
                if tf == 0:
                    continue
                denom = tf + self.k1 * (1 - self.b + self.b * dl / self._avgdl)
                score += self._idf(term) * (tf * (self.k1 + 1) / denom)
            scores.append(score)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        best = [r for r in ranked if scores[r] > 0.0][:k]
        return [ScoredPassage(index=i, passage=self.passages[i], score=scores[i]) for i in best]


def index_passages(passages: list[str]) -> Bm25Scorer:
    return Bm25Scorer(passages=passages)
