"""Project discovery — scans directories for git repos and CLAUDE.md files."""

from pathlib import Path

from fastapi import APIRouter

from .config import config

router = APIRouter()

_project_cache: list[dict] | None = None


def scan_projects(force: bool = False) -> list[dict]:
    """Scan configured root directories for projects (dirs with .git or CLAUDE.md)."""
    global _project_cache
    if _project_cache is not None and not force:
        return _project_cache

    projects = []
    for root in config.project_scan_roots:
        root_path = Path(root)
        if not root_path.is_dir():
            continue
        for child in sorted(root_path.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            has_git = (child / ".git").exists()
            has_claude = (child / "CLAUDE.md").exists()
            if has_git or has_claude:
                projects.append({
                    "name": child.name,
                    "path": str(child),
                    "has_git": has_git,
                    "has_claude_md": has_claude,
                })
    _project_cache = projects
    return projects


def fuzzy_match_project(name: str) -> dict | None:
    """Find the best matching project for a voice-spoken name."""
    from Levenshtein import ratio

    projects = scan_projects()
    name_lower = name.lower().strip()

    # Exact match first
    for p in projects:
        if p["name"].lower() == name_lower:
            return p

    # Substring match
    for p in projects:
        if name_lower in p["name"].lower() or p["name"].lower() in name_lower:
            return p

    # Fuzzy match with Levenshtein
    best_match = None
    best_score = 0.0
    for p in projects:
        score = ratio(name_lower, p["name"].lower())
        if score > best_score:
            best_score = score
            best_match = p
    if best_score >= 0.5:
        return best_match

    return None


@router.get("/projects")
async def list_projects(rescan: bool = False):
    """List all discovered projects."""
    return {"projects": scan_projects(force=rescan)}


@router.get("/projects/match/{name}")
async def match_project(name: str):
    """Fuzzy-match a project by name."""
    match = fuzzy_match_project(name)
    if match:
        return {"match": match}
    return {"match": None, "error": f"No project found matching '{name}'"}
