"""factful CLI entry point."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from yaml import safe_dump

from factful import __version__
from factful.agents.writer import strip_claim_tags
from factful.config import load_settings
from factful.llm import ModelRouter, OpenRouterClient
from factful.pipeline import DEFAULT_ANGLE, PipelineResult, run_pipeline
from factful.report import render_report, serialize_report
from factful.runtime import build_runtime
from factful.style.analyzer import extract_style
from factful.style.io import load_profile


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
    generate.add_argument("prompt", type=str, help="generation prompt describing the article to write")
    generate.add_argument("--angle", type=str, default=DEFAULT_ANGLE, help="framing angle")
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
    install_ffmpeg = sub.add_parser(
        "install-ffmpeg", parents=[common], help="download portable FFmpeg if not on PATH"
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


def _write_outputs(
    out_dir: Path, result: PipelineResult, *, now: datetime | None = None
) -> tuple[Path, Path, Path]:
    generated_at = now or datetime.now().astimezone()
    slug_dir = out_dir / f"{_slugify(result.state.prompt)}-{generated_at:%Y-%m-%d_%H-%M}"
    slug_dir.mkdir(parents=True, exist_ok=True)
    draft_path = slug_dir / "draft.md"
    report_path = slug_dir / "report.md"
    json_path = slug_dir / "report.json"
    draft_path.write_text(strip_claim_tags(result.state.draft or ""), encoding="utf-8")
    report_path.write_text(render_report(result), encoding="utf-8")
    json_path.write_text(json.dumps(serialize_report(result), indent=2), encoding="utf-8")
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
    env = dict(os.environ)
    api_key = env.get("LLM_API_KEY")
    if not api_key:
        raise SystemExit("LLM_API_KEY is not set; cannot run article generation")
    tavily_key = env.get("TAVILY_API_KEY")
    if not tavily_key:
        raise SystemExit("TAVILY_API_KEY is not set; cannot run article generation")

    runtime = build_runtime(env)
    profile = load_profile(
        Path("src/factful/style/profiles") / f"{runtime.settings.writer.profile}.yaml"
    )
    result = run_pipeline(
        args.prompt,
        args.angle,
        settings=runtime.settings,
        searcher=runtime.searcher,
        fetcher=runtime.fetcher,
        clients=runtime.clients,
        profile=profile,
        max_sources=args.max_sources,
        instructions=_load_instructions(
            args, max_chars=runtime.settings.writer.max_instructions_chars
        ),
    )

    scores = ", ".join(f"{record.score:.0f}" for record in result.state.passes)
    print(f"{result.state.prompt} — {result.decision}: {result.reason} (scores: [{scores}])")
    for path in _write_outputs(Path(args.out), result):
        print(f"wrote {path}")
    if result.unresolved:
        for verdict in result.unresolved:
            print(f"UNVERIFIED: {verdict.claim_id} [{verdict.status}] — {verdict.reason}")
    return 0


def _install_ffmpeg_command() -> int:
    from factful.video.ffmpeg import install_ffmpeg

    path = install_ffmpeg()
    print(f"FFmpeg installed at {path}")
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
    if args.command == "install-ffmpeg":
        return _install_ffmpeg_command()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
