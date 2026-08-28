"""Pipeline report rendering and serialization."""

from __future__ import annotations

from typing import Any

from factful.pipeline import PipelineResult


def render_report(result: PipelineResult) -> str:
    state = result.state
    lines = [
        "# Factful report",
        "",
        f"Prompt: {state.prompt}",
        f"Angle: {state.angle}",
        f"Decision: {result.decision}",
        f"Reason: {result.reason}",
        "",
        "## Passes",
        "",
        "| pass | score | critical failures |",
        "| --- | --- | --- |",
    ]
    for index, record in enumerate(state.passes, start=1):
        lines.append(f"| {index} | {record.score:.0f} | {record.critical_failures} |")
    lines += ["", "## Draft", "", state.draft or "", ""]
    lines += ["", "## Fact-check verdicts", ""]
    for verdict in state.verdicts:
        lines.append(
            f"- {verdict.claim_id} [{verdict.status}] confidence={verdict.confidence:.2f}: "
            f"{verdict.reason}"
        )
        if verdict.corroborations:
            lines.append(f"  corroborations: {', '.join(verdict.corroborations)}")
        if verdict.flags:
            lines.append(f"  flags: {', '.join(verdict.flags)}")
    lines += ["", "## Critique", ""]
    for report in state.critiques:
        lines.append(f"Score: {report.score} (verdict {report.verdict})")
        for issue in report.issues:
            lines.append(f"- [{issue.severity}] {issue.type}: {issue.message}")
            if issue.revision:
                lines.append(f"  revision: {issue.revision}")
    lines += ["", "## Sources", ""]
    for citation in state.citations:
        lines.append(f"- [{citation.claim_id}] {citation.claim} — {citation.source_url}")
    lines += ["", "## Unresolved claims", ""]
    if result.unresolved:
        sources_by_id = {c.claim_id: c.source_url for c in state.citations}
        for verdict in result.unresolved:
            source = sources_by_id.get(verdict.claim_id, "unknown")
            lines.append(
                f"- [UNVERIFIED: {verdict.claim_id}] status={verdict.status} "
                f"({verdict.reason}) — source: {source}"
            )
    else:
        lines.append("- (none)")
    return "\n".join(lines)


def serialize_report(result: PipelineResult) -> dict[str, Any]:
    state = result.state
    return {
        "prompt": state.prompt,
        "angle": state.angle,
        "decision": result.decision,
        "reason": result.reason,
        "passes": [
            {"pass": i, "score": record.score, "critical_failures": record.critical_failures}
            for i, record in enumerate(state.passes, start=1)
        ],
        "draft": state.draft,
        "verdicts": [v.model_dump() for v in state.verdicts],
        "critiques": [c.model_dump() for c in state.critiques],
        "sources": [c.model_dump(mode="json") for c in state.citations],
        "unresolved": [v.model_dump() for v in result.unresolved],
    }
