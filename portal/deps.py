"""Shared dependencies for portal routes (breaks circular imports)."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

_portal_dir = Path(__file__).parent
templates = Jinja2Templates(directory=_portal_dir / "templates")


def get_templates() -> Jinja2Templates:
    return templates
