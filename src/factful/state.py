from __future__ import annotations

from dataclasses import dataclass, field

from factful.schemas import Citation, CritiqueReport, FactVerdict, SourceBundle

CRITICAL_STATUSES = {"contradicted", "unsupported"}


@dataclass(frozen=True)
class PassRecord:
    score: float
    draft: str
    critical_failures: int
    title: str = ""


@dataclass
class PipelineState:
    prompt: str
    angle: str
    source_bundle: SourceBundle | None = None
    draft: str | None = None
    score: float | None = None
    title: str | None = None
    verdicts: list[FactVerdict] = field(default_factory=list)
    critiques: list[CritiqueReport] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    pass_: int = 1
    passes: list[PassRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.source_bundle is not None:
            self.citations = list(self.source_bundle.citations)

    @property
    def critical_failures(self) -> int:
        return sum(1 for v in self.verdicts if v.status in CRITICAL_STATUSES)

    def add_verdict(self, verdict: FactVerdict) -> None:
        self.verdicts.append(verdict)

    def add_critique(self, critique: CritiqueReport) -> None:
        self.critiques.append(critique)

    def record_pass(self, score: float, draft: str, title: str = "") -> None:
        self.score = score
        self.draft = draft
        self.title = title or self.title
        self.passes.append(
            PassRecord(
                score=score,
                draft=draft,
                critical_failures=self.critical_failures,
                title=title,
            )
        )

    def advance_pass(self) -> None:
        self.pass_ += 1
        self.verdicts = []
        self.critiques = []
