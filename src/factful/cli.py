"""factful CLI entry point."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from yaml import safe_dump

from factful import __version__
from factful.config import load_settings
from factful.llm import ModelRouter, OpenRouterClient
from factful.style.analyzer import extract_style


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="factful",
        description="Agentic, fact-grounded Substack article generator",
    )
    parser.add_argument("--version", action="version", version=f"factful {__version__}")
    sub = parser.add_subparsers(dest="command")
    generate = sub.add_parser("generate", help="generate an article")
    generate.add_argument("topic", type=str, help="article topic")
    style = sub.add_parser("style", help="extract a writing-style profile from samples")
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "generate":
        print(f"generate: {args.topic} (not yet implemented)")
        return 0
    if args.command == "style":
        return _style_command(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
