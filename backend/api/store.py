"""
DC Feasibility Tool v4 — JSON File Store
==========================================
Simple file-backed storage for sites and weather data.

Why JSON files instead of a database:
    - A feasibility tool manages ~5–20 sites, not millions of rows.
    - JSON files are human-readable (you can inspect them in a text editor).
    - No database setup, migration, or ORM complexity.
    - Easy backup: just copy the data/ folder.
    - The Architecture Agreement specifies backend/data/sites/ for site storage.

Storage layout:
    backend/data/sites/{uuid}.json     — One file per site
    backend/data/weather/{uuid}.json   — Cached weather data per site

Thread safety:
    FastAPI runs async handlers. For this tool's scale (single user,
    few sites), file operations are fine without locking. If this ever
    needs multi-user support, swap this module for SQLite or Postgres.
"""

import json
import shutil
import uuid
from pathlib import Path
from typing import Optional

from engine.models import Site


# ─────────────────────────────────────────────────────────────
# Storage paths — relative to backend/ directory
# ─────────────────────────────────────────────────────────────

# Path.cwd() is typically the backend/ directory when running uvicorn
# from there. We use absolute paths derived from this file's location
# to be safe regardless of where the server is started.
_BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
SITES_DIR = _BASE_DIR / "data" / "sites"
WEATHER_DIR = _BASE_DIR / "data" / "weather"
SOLAR_DIR = _BASE_DIR / "data" / "solar"
GRID_CONTEXT_DIR = _BASE_DIR / "data" / "grid_context"
GRID_EVIDENCE_DIR = _BASE_DIR / "data" / "grid_evidence"

# Create directories if they don't exist (safe to call multiple times)
SITES_DIR.mkdir(parents=True, exist_ok=True)
WEATHER_DIR.mkdir(parents=True, exist_ok=True)
SOLAR_DIR.mkdir(parents=True, exist_ok=True)
GRID_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
GRID_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────
# Site Storage
# ─────────────────────────────────────────────────────────────

def _site_path(site_id: str) -> Path:
    """Get the file path for a site by its ID."""
    return SITES_DIR / f"{site_id}.json"


def create_site(site: Site) -> tuple[str, Site]:
    """Save a new site and return its assigned ID.

    Each site gets a UUID v4 as its identifier. The site data is
    stored as a JSON file named {uuid}.json.

    Args:
        site: Validated Site model from the request body.

    Returns:
        Tuple of (site_id, site) — the ID is a UUID string.
    """
    site_id = str(uuid.uuid4())
    data = {
        "id": site_id,
        "site": site.model_dump(mode="json"),
    }
    _site_path(site_id).write_text(json.dumps(data, indent=2))
    return site_id, site


def get_site(site_id: str) -> Optional[tuple[str, Site]]:
    """Load a site by its ID.

    Returns None if the site doesn't exist (rather than raising),
    so the route handler can return a clean 404.

    Args:
        site_id: UUID string.

    Returns:
        Tuple of (site_id, Site) or None if not found.
    """
    path = _site_path(site_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    site = Site(**data["site"])
    return data["id"], site


def list_sites() -> list[dict]:
    """List all saved sites.

    Returns a list of dicts with 'id' and 'site' keys,
    sorted by site name for consistent ordering.

    Returns:
        List of {"id": str, "site": dict} entries.
    """
    sites = []
    for path in SITES_DIR.glob("*.json"):
        data = json.loads(path.read_text())
        sites.append({
            "id": data["id"],
            "site": data["site"],
        })
    # Sort by site name for consistent display order
    sites.sort(key=lambda s: s["site"].get("name", ""))
    return sites


def count_sites() -> int:
    """Return the number of saved site JSON files."""
    return sum(1 for _ in SITES_DIR.glob("*.json"))


def update_site(site_id: str, site: Site) -> Optional[Site]:
    """Update an existing site.

    Overwrites the JSON file with the new site data.
    Returns None if the site doesn't exist.

    Args:
        site_id: UUID string of the site to update.
        site: New site data (validated Pydantic model).

    Returns:
        Updated Site or None if not found.
    """
    path = _site_path(site_id)
    if not path.exists():
        return None
    data = {
        "id": site_id,
        "site": site.model_dump(mode="json"),
    }
    path.write_text(json.dumps(data, indent=2))
    return site


def delete_site(site_id: str) -> bool:
    """Delete a site by its ID.

    Also removes any cached weather data for this site.

    Args:
        site_id: UUID string.

    Returns:
        True if deleted, False if not found.
    """
    path = _site_path(site_id)
    if not path.exists():
        return False
    path.unlink()
    # Also clean up cached weather data
    weather_path = _weather_path(site_id)
    if weather_path.exists():
        weather_path.unlink()
    delete_solar_cache(site_id)
    delete_grid_context(site_id)
    delete_grid_official_evidence(site_id)
    return True


# ─────────────────────────────────────────────────────────────
# Weather Data Cache
# ─────────────────────────────────────────────────────────────
# Weather data is expensive to fetch (Open-Meteo API call for 5 years).
# We cache it per site so re-running scenarios doesn't re-fetch.

def _weather_path(site_id: str) -> Path:
    """Get the file path for cached weather data."""
    return WEATHER_DIR / f"{site_id}.json"


def save_weather(site_id: str, weather_dict: dict) -> None:
    """Cache weather data for a site.

    The weather_dict is the serialized form of WeatherData — we store
    it as a dict rather than the dataclass because JSON files don't
    handle dataclasses natively. The API layer converts between formats.

    Args:
        site_id: UUID of the site this weather belongs to.
        weather_dict: Serialized weather data dict.
    """
    _weather_path(site_id).write_text(json.dumps(weather_dict))


def get_weather(site_id: str) -> Optional[dict]:
    """Load cached weather data for a site.

    Returns None if no weather data is cached.

    Args:
        site_id: UUID string.

    Returns:
        Weather data dict or None.
    """
    path = _weather_path(site_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def has_weather(site_id: str) -> bool:
    """Check if weather data is cached for a site.

    Lightweight check without loading the data — useful for
    the Site Manager page to show weather fetch status icons.

    Args:
        site_id: UUID string.

    Returns:
        True if cached weather exists.
    """
    return _weather_path(site_id).exists()


def count_weather_caches() -> int:
    """Return the number of cached weather files."""
    return sum(1 for _ in WEATHER_DIR.glob("*.json"))


def clear_weather_cache(site_id: Optional[str] = None) -> int:
    """Delete cached weather for one site or for all sites.

    Returns the number of files removed.
    """
    if site_id is not None:
        path = _weather_path(site_id)
        if path.exists():
            path.unlink()
            return 1
        return 0

    removed = 0
    for path in WEATHER_DIR.glob("*.json"):
        path.unlink()
        removed += 1
    return removed


# ─────────────────────────────────────────────────────────────
# Solar Profile Cache
# ─────────────────────────────────────────────────────────────

def _grid_context_site_dir(site_id: str) -> Path:
    """Directory containing all cached grid-context responses for one site."""
    return GRID_CONTEXT_DIR / site_id


def _grid_context_path(site_id: str, radius_key: str) -> Path:
    """Path for one cached grid-context response."""
    return _grid_context_site_dir(site_id) / f"{radius_key}.json"


def save_grid_context(site_id: str, radius_key: str, result: dict) -> None:
    """Cache one grid-context response for a site and radius key."""
    site_dir = _grid_context_site_dir(site_id)
    site_dir.mkdir(parents=True, exist_ok=True)
    _grid_context_path(site_id, radius_key).write_text(json.dumps(result, indent=2))


def get_grid_context(site_id: str, radius_key: str) -> Optional[dict]:
    """Load one cached grid-context response if it exists."""
    path = _grid_context_path(site_id, radius_key)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def delete_grid_context(site_id: str) -> bool:
    """Delete all cached grid-context responses for a site."""
    site_dir = _grid_context_site_dir(site_id)
    if not site_dir.exists():
        return False
    shutil.rmtree(site_dir)
    return True


def count_grid_context_caches() -> int:
    """Return the total number of cached grid-context JSON payloads."""
    if not GRID_CONTEXT_DIR.exists():
        return 0

    total = 0
    for site_dir in GRID_CONTEXT_DIR.iterdir():
        if site_dir.is_dir():
            total += sum(1 for _ in site_dir.glob("*.json"))
    return total


def _grid_official_evidence_path(site_id: str) -> Path:
    """Path for one site's saved official-evidence overlay."""
    return GRID_EVIDENCE_DIR / f"{site_id}.json"


def save_grid_official_evidence(site_id: str, evidence: dict) -> None:
    """Persist one site's manual official-evidence overlay."""
    GRID_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    _grid_official_evidence_path(site_id).write_text(json.dumps(evidence, indent=2))


def get_grid_official_evidence(site_id: str) -> Optional[dict]:
    """Load a site's saved official-evidence overlay if present."""
    path = _grid_official_evidence_path(site_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def delete_grid_official_evidence(site_id: str) -> bool:
    """Delete a site's saved official-evidence overlay."""
    path = _grid_official_evidence_path(site_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def _solar_site_dir(site_id: str) -> Path:
    """Directory containing cached solar profiles for one site."""
    return SOLAR_DIR / site_id


def _solar_profile_path(site_id: str, profile_key: str) -> Path:
    """Path for one cached normalized PV profile."""
    return _solar_site_dir(site_id) / f"{profile_key}.json"


def save_solar_profile(site_id: str, profile_key: str, solar_dict: dict) -> None:
    """Cache a normalized PV profile for a site and PVGIS parameter set."""
    site_dir = _solar_site_dir(site_id)
    site_dir.mkdir(parents=True, exist_ok=True)
    _solar_profile_path(site_id, profile_key).write_text(json.dumps(solar_dict, indent=2))


def get_solar_profile(site_id: str, profile_key: str) -> Optional[dict]:
    """Load one cached normalized PV profile."""
    path = _solar_profile_path(site_id, profile_key)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def has_solar_profile(site_id: str, profile_key: str) -> bool:
    """Check whether a cached normalized PV profile exists."""
    return _solar_profile_path(site_id, profile_key).exists()


def delete_solar_cache(site_id: str, profile_key: Optional[str] = None) -> None:
    """Delete one cached PV profile or all solar cache for a site."""
    if profile_key is not None:
        path = _solar_profile_path(site_id, profile_key)
        if path.exists():
            path.unlink()
        site_dir = _solar_site_dir(site_id)
        if site_dir.exists() and not any(site_dir.iterdir()):
            site_dir.rmdir()
        return

    site_dir = _solar_site_dir(site_id)
    if site_dir.exists():
        shutil.rmtree(site_dir)


def has_any_solar_profile(site_id: str) -> bool:
    """Check whether any cached solar profile exists for a site."""
    site_dir = _solar_site_dir(site_id)
    if not site_dir.exists():
        return False
    return any(site_dir.glob("*.json"))


def count_solar_sites() -> int:
    """Return how many site directories currently have cached solar data."""
    return sum(1 for path in SOLAR_DIR.iterdir() if path.is_dir())


def count_solar_profiles() -> int:
    """Return the total number of cached normalized PV profiles."""
    total = 0
    for site_dir in SOLAR_DIR.iterdir():
        if site_dir.is_dir():
            total += sum(1 for _ in site_dir.glob("*.json"))
    return total


def clear_all_solar_cache() -> int:
    """Delete all cached solar profiles and return the number removed."""
    removed = count_solar_profiles()
    for site_dir in list(SOLAR_DIR.iterdir()):
        if site_dir.is_dir():
            shutil.rmtree(site_dir)
        else:
            site_dir.unlink()
    return removed
