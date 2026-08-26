"""Pipeline orchestrator: gather, write, fact-check, critique, and converge."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from factful.agents._urls import extract_urls
from factful.agents.critic import critique, word_count
from factful.agents.factcheck import factcheck_article
from factful.agents.fetch import Fetcher
from factful.agents.gather import gather
from factful.agents.search import Searcher
from factful.agents.writer import revise_article, write_article
from factful.config import Settings
from factful.llm.client import ChatClient
from factful.schemas import FactVerdict
from factful.state import CRITICAL_STATUSES, PassRecord, PipelineState
from factful.style.schema import StyleProfile

logger = logging.getLogger(__name__)

Decision = Literal["publish", "patch", "stop"]

DEFAULT_ANGLE = "explore the topic through key numbers and statistics"


@dataclass(frozen=True)
class PipelineClients:
    gather: ChatClient
    writer: ChatClient
    factcheck: ChatClient
    critic: ChatClient


@dataclass(frozen=True)
class ConvergeResult:
    decision: Decision
    reason: str


@dataclass(frozen=True)
class PipelineResult:
    state: PipelineState
    decision: Decision
    reason: str
    unresolved: list[FactVerdict] = field(default_factory=list)


def converge(
    *,
    score: float,
    critical_failures: int,
    pass_: int,
    settings: Settings,
    history: list[PassRecord],
    words: int,
) -> ConvergeResult:
    """Decide whether to publish, patch again, or stop after a pass."""
    in_bounds = settings.writer.min_words <= words <= settings.writer.max_words
    if in_bounds and critical_failures == 0 and score >= settings.pipeline.score_accept:
        return ConvergeResult(decision="publish", reason="hard gate passed")
    if pass_ >= settings.pipeline.max_passes:
        return ConvergeResult(decision="stop", reason="max passes reached")
    if not in_bounds:
        return ConvergeResult(decision="patch", reason="word count out of bounds; patching")
    previous = history[-1].score if history else None
    if previous is not None and score < previous:
        return ConvergeResult(decision="stop", reason="score regressed (oscillation guard)")
    if previous is not None and score - previous < settings.pipeline.epsilon:
        return ConvergeResult(decision="stop", reason="diminishing returns")
    return ConvergeResult(decision="patch", reason="below gate; patching")


def run_pipeline(
    topic: str,
    angle: str,
    *,
    settings: Settings,
    searcher: Searcher,
    fetcher: Fetcher,
    clients: PipelineClients,
    profile: StyleProfile,
    max_sources: int | None = None,
    today: date | None = None,
    instructions: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> PipelineResult:
    progress = on_progress or _noop_progress
    progress("gathering sources")

    user_urls = list(dict.fromkeys(extract_urls(topic) + extract_urls(instructions or "")))

    bundle = gather(
        topic,
        angle,
        client=clients.gather,
        searcher=searcher,
        fetcher=fetcher,
        settings=settings,
        max_sources=max_sources,
        today=today,
        user_urls=user_urls or None,
    )
    state = PipelineState(topic=topic, angle=angle, source_bundle=bundle)
    logger.info("gathered %d citations", len(state.citations))

    previous_draft = None
    previous_verdicts: list[FactVerdict] = []
    previous_critique = None

    for pass_ in range(1, settings.pipeline.max_passes + 1):
        progress("writing draft")
        if state.pass_ == 1 or settings.pipeline.revision_mode == "regenerate":
            draft = write_article(
                bundle,
                profile,
                client=clients.writer,
                settings=settings,
                instructions=instructions,
                today=today,
                temperature=temperature,
                top_p=top_p,
            )
            logger.info("pass %d: wrote draft", pass_)
        else:
            if previous_draft is None or previous_critique is None:
                raise RuntimeError("cannot patch pass 1 without prior feedback")
            draft = revise_article(
                previous_draft,
                previous_verdicts,
                previous_critique,
                bundle,
                profile,
                client=clients.writer,
                settings=settings,
                instructions=instructions,
                today=today,
                temperature=temperature,
                top_p=top_p,
            )
            logger.info("pass %d: revised draft", pass_)

        progress("fact-checking")
        for verdict in factcheck_article(
            draft,
            bundle.citations,
            fetcher=fetcher,
            client=clients.factcheck,
            settings=settings,
            today=today,
        ):
            state.add_verdict(verdict)
        logger.info(
            "pass %d: fact-checked %d claims (%d critical)",
            pass_,
            len(state.verdicts),
            state.critical_failures,
        )
        progress("critiquing")
        report = critique(draft, client=clients.critic, settings=settings)
        state.add_critique(report)
        state.record_pass(score=report.score, draft=draft.markdown)
        logger.info("pass %d: critique score %g", pass_, report.score)

        decision = converge(
            score=report.score,
            critical_failures=state.critical_failures,
            pass_=pass_,
            settings=settings,
            history=state.passes[:-1],
            words=word_count(draft.markdown),
        )
        if decision.decision != "patch":
            logger.info("decision: %s (%s)", decision.decision, decision.reason)
            result = PipelineResult(
                state=state,
                decision=decision.decision,
                reason=decision.reason,
                unresolved=[v for v in state.verdicts if v.status in CRITICAL_STATUSES],
            )
            if decision.decision != "publish" and state.passes:
                best = max(state.passes, key=lambda p: p.score)
                state.draft = best.draft
            return result

        previous_draft = draft
        previous_verdicts = list(state.verdicts)
        previous_critique = report
        state.advance_pass()

    raise RuntimeError("convergence loop exceeded max_passes without deciding")


def _noop_progress(stage: str) -> None:
    return
