"""factful CLI entry point."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from yaml import safe_dump

from factful import __version__
from factful.agents.fetch import HttpxFetcher
from factful.agents.search import TavilySearcher
from factful.config import load_settings
from factful.llm import ModelRouter, OpenRouterClient
from factful.pipeline import PipelineClients, PipelineResult, run_pipeline
from factful.style.analyzer import extract_style
from factful.style.io import load_profile

_DEFAULT_ANGLE = "explore the topic through key numbers and statistics"


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
        help="log pipeline progress to stderr",
    )
    parser = argparse.ArgumentParser(
        prog="factful",
        parents=[common],
        description="Agentic, fact-grounded Substack article generator",
    )
    parser.add_argument("--version", action="version", version=f"factful {__version__}")
    sub = parser.add_subparsers(dest="command")
    generate = sub.add_parser("generate", parents=[common], help="generate an article")
    generate.add_argument("topic", type=str, help="article topic")
    generate.add_argument("--angle", type=str, default=_DEFAULT_ANGLE, help="framing angle")
    generate.add_argument(
        "--max-sources",
        type=int,
        help="cap on sources gathered (default: settings.gather.max_sources)",
    )
    generate.add_argument(
        "--instructions",
        type=str,
        help="optional writer instructions for the article",
    )
    generate.add_argument(
        "--instructions-file",
        type=Path,
        help="path to a file with writer instructions (mutually exclusive with --instructions)",
    )
    generate.add_argument("--out", type=str, default="output", help="output directory")
    style = sub.add_parser(
        "style", parents=[common], help="extract a writing-style profile from samples"
    )
    style.add_argument("samples", type=str, nargs="+", help="sample article markdown files")
    style.add_argument("--name", type=str, default="voice", help="profile/voice name")
    style.add_argument(
        "--out",
        type=str,
        help="output Profile YAML path (default: profiles/<name>.yaml)",
    )
    return parser


def _style_command(args: argparse.Namespace) -> int:
    settings = load_settings()
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise SystemExit("LLM_API_KEY is not set; cannot run style extraction")
    env: dict[str, str] = dict(os.environ)
    model = ModelRouter(settings, env=env).resolve("style")

    samples = [Path(p).read_text(encoding="utf-8") for p in args.samples]
    client = OpenRouterClient(model=model, api_key=api_key, base_url=settings.llm.base_url)
    profile = extract_style(samples, name=args.name, client=client)

    out = Path(args.out) if args.out else Path("src/factful/style/profiles") / f"{args.name}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(safe_dump(profile.model_dump(), sort_keys=False), encoding="utf-8")
    print(f"wrote {out}")
    return 0


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "article"


def _render_report(result: PipelineResult) -> str:
    state = result.state
    lines = [
        "# Factful report",
        "",
        f"Topic: {state.topic}",
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


def _serialize_report(result: PipelineResult) -> dict[str, Any]:
    state = result.state
    return {
        "topic": state.topic,
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


def _write_outputs(out_dir: Path, result: PipelineResult) -> tuple[Path, Path, Path]:
    slug_dir = out_dir / _slugify(result.state.topic)
    slug_dir.mkdir(parents=True, exist_ok=True)
    draft_path = slug_dir / "draft.md"
    report_path = slug_dir / "report.md"
    json_path = slug_dir / "report.json"
    draft_path.write_text(result.state.draft or "", encoding="utf-8")
    report_path.write_text(_render_report(result), encoding="utf-8")
    json_path.write_text(json.dumps(_serialize_report(result), indent=2), encoding="utf-8")
    return draft_path, report_path, json_path


def _load_instructions(args: argparse.Namespace, *, max_chars: int) -> str | None:
    inline: str | None = args.instructions
    file_path: Path | None = args.instructions_file
    if inline is not None and file_path is not None:
        raise SystemExit("--instructions and --instructions-file are mutually exclusive")
    if file_path is not None:
        try:
            instructions: str | None = file_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise SystemExit(f"instructions file {file_path} is not valid UTF-8: {exc}") from exc
        except OSError as exc:
            raise SystemExit(f"cannot read instructions file {file_path}: {exc}") from exc
    else:
        instructions = inline
    if instructions is not None and len(instructions) > max_chars:
        raise SystemExit(f"instructions too long ({len(instructions)} chars; max {max_chars})")
    return instructions


def _generate_command(args: argparse.Namespace) -> int:
    load_dotenv()
    env: dict[str, str] = dict(os.environ)
    api_key = env.get("LLM_API_KEY")
    if not api_key:
        raise SystemExit("LLM_API_KEY is not set; cannot run article generation")
    tavily_key = env.get("TAVILY_API_KEY")
    if not tavily_key:
        raise SystemExit("TAVILY_API_KEY is not set; cannot run article generation")

    settings = load_settings()
    router = ModelRouter(settings, env=env)
    base_url = settings.llm.base_url
    clients = PipelineClients(
        gather=OpenRouterClient(model=router.resolve("gather"), api_key=api_key, base_url=base_url),
        writer=OpenRouterClient(model=router.resolve("writer"), api_key=api_key, base_url=base_url),
        factcheck=OpenRouterClient(
            model=router.resolve("factcheck"), api_key=api_key, base_url=base_url
        ),
        critic=OpenRouterClient(model=router.resolve("critic"), api_key=api_key, base_url=base_url),
    )
    profile = load_profile(Path("src/factful/style/profiles") / f"{settings.writer.profile}.yaml")
    result = run_pipeline(
        args.topic,
        args.angle,
        settings=settings,
        searcher=TavilySearcher(api_key=tavily_key, days=settings.gather.search_days),
        fetcher=HttpxFetcher(),
        clients=clients,
        profile=profile,
        max_sources=args.max_sources,
        instructions=_load_instructions(args, max_chars=settings.writer.max_instructions_chars),
    )

    scores = ", ".join(f"{record.score:.0f}" for record in result.state.passes)
    print(f"{result.state.topic} — {result.decision}: {result.reason} (scores: [{scores}])")
    for path in _write_outputs(Path(args.out), result):
        print(f"wrote {path}")
    if result.unresolved:
        for verdict in result.unresolved:
            print(f"UNVERIFIED: {verdict.claim_id} [{verdict.status}] — {verdict.reason}")
    return 0


def _configure_logging(verbose: bool) -> None:
    logger = logging.getLogger("factful")
    logger.setLevel(logging.INFO if verbose else logging.WARNING)
    for handler in list(logger.handlers):
        if isinstance(handler, logging.StreamHandler):
            logger.removeHandler(handler)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[factful] %(asctime)s %(message)s"))
    logger.addHandler(handler)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(bool(getattr(args, "verbose", False)))
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "generate":
        return _generate_command(args)
    if args.command == "style":
        return _style_command(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
