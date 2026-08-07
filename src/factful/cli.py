"""factful CLI entry point."""

from __future__ import annotations

import argparse

from factful import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="factful",
        description="Agentic, fact-grounded Substack article generator",
    )
    parser.add_argument("--version", action="version", version=f"factful {__version__}")
    sub = parser.add_subparsers(dest="command")
    generate = sub.add_parser("generate", help="generate an article")
    generate.add_argument("topic", type=str, help="article topic")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "generate":
        print(f"generate: {args.topic} (not yet implemented)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
