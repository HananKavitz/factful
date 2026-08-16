"""Serve the built React SPA from the FastAPI app."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def default_frontend_dist() -> Path:
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


def mount_frontend(app: FastAPI, dist_dir: Path) -> None:
    """Serve a built SPA from dist_dir, falling back to index.html for client routes."""
    root = dist_dir.resolve()
    index = root / "index.html"
    if not index.is_file():
        return
    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa_fallback(path: str) -> FileResponse:
        candidate = (root / path).resolve()
        if path and candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)
