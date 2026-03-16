import asyncio
import io
from datetime import datetime, timedelta, timezone

import pytest
from starlette.datastructures import UploadFile

from api import routes_climate
from engine.models import Site


def _manual_weather_csv(*, include_humidity: bool = True) -> str:
    header = ["timestamp_utc", "dry_bulb_c"]
    if include_humidity:
        header.append("relative_humidity_pct")

    rows = [",".join(header)]
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    for hour in range(8760):
        timestamp = (start + timedelta(hours=hour)).isoformat().replace("+00:00", "Z")
        row = [timestamp, f"{12 + (hour % 24) * 0.25:.2f}"]
        if include_humidity:
            row.append(f"{60 + (hour % 5):.1f}")
        rows.append(",".join(row))
    return "\n".join(rows)


def test_upload_weather_endpoint_saves_manual_cache(monkeypatch):
    saved: dict[str, object] = {}

    monkeypatch.setattr(
        routes_climate,
        "get_site",
        lambda site_id: (
            site_id,
            Site(name="Manual Weather Site", land_area_m2=25000, latitude=None, longitude=None),
        ),
    )

    def fake_save_weather(site_id: str, payload: dict):
        saved["site_id"] = site_id
        saved["payload"] = payload

    monkeypatch.setattr(routes_climate, "save_weather", fake_save_weather)

    upload = UploadFile(
        filename="manual-weather.csv",
        file=io.BytesIO(_manual_weather_csv().encode("utf-8")),
    )

    result = asyncio.run(
        routes_climate.upload_weather_endpoint(site_id="site-1", file=upload)
    )

    assert result.site_id == "site-1"
    assert result.source_type == "manual_upload"
    assert result.original_filename == "manual-weather.csv"
    assert result.has_humidity is True
    assert result.hours == 8760
    assert saved["site_id"] == "site-1"
    assert saved["payload"]["source_type"] == "manual_upload"
    assert saved["payload"]["original_filename"] == "manual-weather.csv"


def test_upload_weather_endpoint_returns_readable_validation_error(monkeypatch):
    monkeypatch.setattr(
        routes_climate,
        "get_site",
        lambda site_id: (site_id, Site(name="Bad Upload", land_area_m2=20000)),
    )

    upload = UploadFile(
        filename="manual-weather.csv",
        file=io.BytesIO("dry_bulb_c\n18.0".encode("utf-8")),
    )

    with pytest.raises(routes_climate.HTTPException) as excinfo:
        asyncio.run(routes_climate.upload_weather_endpoint(site_id="site-2", file=upload))

    assert excinfo.value.status_code == 400
    assert "8760 hourly rows" in excinfo.value.detail


def test_get_weather_endpoint_reports_manual_metadata(monkeypatch):
    monkeypatch.setattr(
        routes_climate,
        "get_weather",
        lambda site_id: {
            "temperatures": [20.0] * 8760,
            "humidities": None,
            "latitude": None,
            "longitude": None,
            "source": "Manual CSV upload (manual-weather.csv)",
            "original_filename": "manual-weather.csv",
            "uploaded_at_utc": "2026-03-12T12:00:00+00:00",
            "hours": 8760,
        },
    )

    result = asyncio.run(routes_climate.get_weather_endpoint("site-3", include_hourly=False))

    assert isinstance(result, routes_climate.WeatherStatusResponse)
    assert result.source_type == "manual_upload"
    assert result.original_filename == "manual-weather.csv"
    assert result.has_humidity is False


def test_delete_weather_endpoint_removes_cache(monkeypatch):
    monkeypatch.setattr(routes_climate, "clear_weather_cache", lambda site_id: 1)

    result = asyncio.run(routes_climate.delete_weather_endpoint("site-4"))

    assert result.model_dump() == {
        "site_id": "site-4",
        "deleted": True,
    }


def test_delete_weather_endpoint_returns_404_when_missing(monkeypatch):
    monkeypatch.setattr(routes_climate, "clear_weather_cache", lambda site_id: 0)

    with pytest.raises(routes_climate.HTTPException) as excinfo:
        asyncio.run(routes_climate.delete_weather_endpoint("site-5"))

    assert excinfo.value.status_code == 404
