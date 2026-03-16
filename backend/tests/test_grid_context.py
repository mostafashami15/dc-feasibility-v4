import asyncio
from pathlib import Path
import shutil

import pytest

from api import routes_grid, store
from engine.grid_context import (
    GRID_CONTEXT_SOURCE_LAYER,
    GridContextProviderError,
    OverpassGridContextProvider,
    ProviderAsset,
    build_grid_context_result,
    make_grid_context_cache_key,
)
from engine.models import (
    GridAssetType,
    GridConfidence,
    GridContextRequest,
    GridGeometryType,
    GridOfficialEvidence,
    Site,
)


class StaticGridContextProvider:
    def __init__(self, assets: list[ProviderAsset]):
        self.assets = assets

    def get_assets(self, **kwargs) -> list[ProviderAsset]:
        del kwargs
        return self.assets


def _site_with_coordinates() -> Site:
    return Site(
        name="Grid Screening Site",
        land_area_m2=20000,
        latitude=45.0,
        longitude=9.0,
    )


def test_build_grid_context_result_sorts_assets_and_builds_summary():
    provider = StaticGridContextProvider(
        [
            ProviderAsset(
                asset_id="line-far",
                asset_type=GridAssetType.LINE,
                name="Mapped 220 kV line",
                operator="Mapped public placeholder",
                voltage_kv=220.0,
                circuits=2,
                geometry_type=GridGeometryType.LINE,
                coordinates=[(45.0, 9.0200), (45.0150, 9.0200)],
                source="mapped_public_fixture",
                confidence=GridConfidence.MAPPED_PUBLIC,
            ),
            ProviderAsset(
                asset_id="substation-near",
                asset_type=GridAssetType.SUBSTATION,
                name="Mapped 132 kV substation",
                operator="Mapped public placeholder",
                voltage_kv=132.0,
                circuits=None,
                geometry_type=GridGeometryType.POINT,
                coordinates=[(45.0050, 9.0050)],
                source="mapped_public_fixture",
                confidence=GridConfidence.MAPPED_PUBLIC,
            ),
            ProviderAsset(
                asset_id="line-near",
                asset_type=GridAssetType.LINE,
                name="Mapped 132 kV corridor",
                operator="Mapped public placeholder",
                voltage_kv=132.0,
                circuits=1,
                geometry_type=GridGeometryType.LINE,
                coordinates=[(44.9990, 9.0010), (45.0010, 9.0030)],
                source="mapped_public_fixture",
                confidence=GridConfidence.MAPPED_PUBLIC,
            ),
        ]
    )

    result = build_grid_context_result(
        site_id="site-1",
        site=_site_with_coordinates(),
        radius_km=5.0,
        provider=provider,
        include_score=True,
    )

    assert [asset.asset_id for asset in result.assets] == [
        "line-near",
        "substation-near",
        "line-far",
    ]
    assert result.summary.nearby_line_count == 2
    assert result.summary.nearby_substation_count == 1
    assert result.summary.nearest_line_km is not None
    assert result.summary.nearest_substation_km is not None
    assert result.summary.nearest_line_km < result.summary.nearest_substation_km
    assert result.summary.max_voltage_kv == pytest.approx(220.0)
    assert result.score is not None
    assert result.score.overall_score > 0
    assert result.score.voltage_score == pytest.approx(24.0)
    assert result.score.distance_score == pytest.approx(35.0)
    assert result.score.substation_score == pytest.approx(20.0)
    assert result.score.evidence_score == pytest.approx(0.0)
    assert any("evidence component stays at 0" in note for note in result.score.notes)
    assert result.analysis_grade == "screening_grade"
    assert result.confidence == "mapped_public"


def test_build_grid_context_result_handles_empty_radius():
    provider = StaticGridContextProvider(
        [
            ProviderAsset(
                asset_id="far-point",
                asset_type=GridAssetType.SUBSTATION,
                name="Far mapped substation",
                operator="Mapped public placeholder",
                voltage_kv=220.0,
                circuits=None,
                geometry_type=GridGeometryType.POINT,
                coordinates=[(45.1000, 9.1000)],
                source="mapped_public_fixture",
                confidence=GridConfidence.MAPPED_PUBLIC,
            )
        ]
    )

    result = build_grid_context_result(
        site_id="site-2",
        site=_site_with_coordinates(),
        radius_km=1.0,
        provider=provider,
        include_score=True,
    )

    assert result.assets == []
    assert result.summary.nearby_line_count == 0
    assert result.summary.nearby_substation_count == 0
    assert result.summary.nearest_line_km is None
    assert result.summary.nearest_substation_km is None
    assert result.score is not None
    assert result.score.overall_score == 0


def test_build_grid_context_result_applies_user_confirmed_evidence_overlay():
    provider = StaticGridContextProvider(
        [
            ProviderAsset(
                asset_id="line-confirmed",
                asset_type=GridAssetType.LINE,
                name="Mapped 220 kV line",
                operator="Mapped public placeholder",
                voltage_kv=220.0,
                circuits=2,
                geometry_type=GridGeometryType.LINE,
                coordinates=[(44.9990, 9.0010), (45.0010, 9.0030)],
                source="mapped_public_fixture",
                confidence=GridConfidence.MAPPED_PUBLIC,
            )
        ]
    )

    result = build_grid_context_result(
        site_id="site-confirmed",
        site=_site_with_coordinates(),
        radius_km=5.0,
        provider=provider,
        include_score=True,
        official_evidence=GridOfficialEvidence(
            utility_or_tso_reference="STMG-2026-001",
            confirmed_substation_name="Official 220 kV station",
            confirmed_voltage_kv=220.0,
            confirmed_requested_mw=80.0,
            connection_status="Under utility review",
        ),
    )

    assert result.confidence == "user_confirmed"
    assert result.official_evidence is not None
    assert result.official_evidence.confirmed_requested_mw == pytest.approx(80.0)
    assert result.score is not None
    assert result.score.evidence_score > 0
    assert "user_confirmed_manual" in result.source_layers
    assert any(note.confidence == "user_confirmed" for note in result.evidence_notes)


def test_make_grid_context_cache_key_is_stable():
    assert make_grid_context_cache_key(5.0) == "5km_v3"
    assert make_grid_context_cache_key(2.5) == "2p5km_v3"


def test_grid_context_store_round_trip(monkeypatch):
    cache_root = Path("data") / "test_grid_context_cache"
    if cache_root.exists():
        shutil.rmtree(cache_root)
    monkeypatch.setattr(store, "GRID_CONTEXT_DIR", cache_root)

    payload = {
        "site_id": "site-cache",
        "site_name": "Cache Test",
        "latitude": 45.0,
        "longitude": 9.0,
        "analysis_grade": "screening_grade",
        "summary": {
            "radius_km": 5.0,
            "nearby_line_count": 1,
            "nearby_substation_count": 0,
            "nearest_line_km": 0.5,
            "nearest_substation_km": None,
            "max_voltage_kv": 132.0,
            "high_voltage_assets_within_radius": 1,
        },
        "score": None,
        "assets": [],
        "evidence_notes": [],
        "official_context_notes": [],
        "source_layers": ["mapped_public_fixture"],
        "confidence": "mapped_public",
        "generated_at_utc": "2026-03-12T12:00:00+00:00",
    }

    try:
        assert store.count_grid_context_caches() == 0

        store.save_grid_context("site-cache", "5km_v3", payload)

        assert store.get_grid_context("site-cache", "5km_v3") == payload
        assert store.count_grid_context_caches() == 1
        assert store.delete_grid_context("site-cache") is True
        assert store.get_grid_context("site-cache", "5km_v3") is None
        assert store.count_grid_context_caches() == 0
    finally:
        if cache_root.exists():
            shutil.rmtree(cache_root)


def test_grid_official_evidence_store_round_trip(monkeypatch):
    evidence_root = Path("data") / "test_grid_evidence"
    if evidence_root.exists():
        shutil.rmtree(evidence_root)
    monkeypatch.setattr(store, "GRID_EVIDENCE_DIR", evidence_root)

    payload = {
        "utility_or_tso_reference": "STMG-2026-002",
        "reference_date": "2026-03-12",
        "confirmed_substation_name": "North Station",
        "confirmed_voltage_kv": 220.0,
        "confirmed_requested_mw": 60.0,
        "confirmed_available_mw": None,
        "connection_status": "Accepted",
        "timeline_status": "Q1 2028 target",
        "notes": "Copied from official letter.",
    }

    try:
        assert store.get_grid_official_evidence("site-evidence") is None

        store.save_grid_official_evidence("site-evidence", payload)

        assert store.get_grid_official_evidence("site-evidence") == payload
        assert store.delete_grid_official_evidence("site-evidence") is True
        assert store.get_grid_official_evidence("site-evidence") is None
    finally:
        if evidence_root.exists():
            shutil.rmtree(evidence_root)


def test_fetch_grid_context_route_requires_coordinates(monkeypatch):
    monkeypatch.setattr(
        routes_grid,
        "get_site",
        lambda site_id: (site_id, Site(name="No Coordinates", land_area_m2=15000)),
    )
    monkeypatch.setattr(routes_grid, "get_grid_context", lambda site_id, radius_key: None)

    request = GridContextRequest(site_id="site-3", radius_km=5.0)

    with pytest.raises(routes_grid.HTTPException) as excinfo:
        asyncio.run(routes_grid.fetch_grid_context_endpoint(request))

    assert excinfo.value.status_code == 400
    assert "no coordinates" in excinfo.value.detail.lower()


def test_get_grid_context_route_returns_cached_payload(monkeypatch):
    site = _site_with_coordinates()
    cached_result = build_grid_context_result(
        site_id="site-4",
        site=site,
        radius_km=5.0,
        provider=StaticGridContextProvider(
            [
                ProviderAsset(
                    asset_id="line-cached",
                    asset_type=GridAssetType.LINE,
                    name="Cached mapped line",
                    operator="Mapped public placeholder",
                    voltage_kv=132.0,
                    circuits=1,
                    geometry_type=GridGeometryType.LINE,
                    coordinates=[(44.9990, 9.0020), (45.0040, 9.0020)],
                    source="mapped_public_fixture",
                    confidence=GridConfidence.MAPPED_PUBLIC,
                )
            ]
        ),
    )

    monkeypatch.setattr(routes_grid, "get_site", lambda site_id: (site_id, site))
    monkeypatch.setattr(
        routes_grid,
        "get_grid_context",
        lambda site_id, radius_key: cached_result.model_dump(mode="json"),
    )

    result = asyncio.run(
        routes_grid.get_grid_context_endpoint("site-4", radius_km=5.0, include_score=False)
    )

    assert result.site_id == "site-4"
    assert result.summary.nearby_line_count == 1
    assert result.assets[0].asset_id == "line-cached"


def test_get_grid_context_route_upgrades_scoreless_cache_when_requested(monkeypatch):
    site = _site_with_coordinates()
    provider = StaticGridContextProvider(
        [
            ProviderAsset(
                asset_id="substation-upgrade",
                asset_type=GridAssetType.SUBSTATION,
                name="Upgrade substation",
                operator="Mapped public placeholder",
                voltage_kv=220.0,
                circuits=None,
                geometry_type=GridGeometryType.POINT,
                coordinates=[(45.0040, 9.0040)],
                source="mapped_public_fixture",
                confidence=GridConfidence.MAPPED_PUBLIC,
            )
        ]
    )
    cached_result = build_grid_context_result(
        site_id="site-4-scoreless",
        site=site,
        radius_km=5.0,
        provider=provider,
        include_score=False,
    )
    scored_result = build_grid_context_result(
        site_id="site-4-scoreless",
        site=site,
        radius_km=5.0,
        provider=provider,
        include_score=True,
    )

    monkeypatch.setattr(routes_grid, "get_site", lambda site_id: (site_id, site))
    monkeypatch.setattr(
        routes_grid,
        "get_grid_context",
        lambda site_id, radius_key: cached_result.model_dump(mode="json"),
    )

    captured: dict[str, object] = {}

    def fake_build_and_cache_result(*, site_id: str, site: Site, radius_km: float, include_score: bool):
        captured["site_id"] = site_id
        captured["radius_km"] = radius_km
        captured["include_score"] = include_score
        return scored_result

    monkeypatch.setattr(routes_grid, "_build_and_cache_result", fake_build_and_cache_result)

    result = asyncio.run(
        routes_grid.get_grid_context_endpoint(
            "site-4-scoreless",
            radius_km=5.0,
            include_score=True,
        )
    )

    assert captured["site_id"] == "site-4-scoreless"
    assert captured["radius_km"] == 5.0
    assert captured["include_score"] is True
    assert result.score is not None
    assert result.score.evidence_score == pytest.approx(0.0)


def test_save_grid_official_evidence_route_invalidates_cached_grid_context(monkeypatch):
    site = _site_with_coordinates()
    deleted: dict[str, object] = {}
    saved: dict[str, object] = {}

    monkeypatch.setattr(routes_grid, "get_site", lambda site_id: (site_id, site))
    monkeypatch.setattr(
        routes_grid,
        "delete_grid_context",
        lambda site_id: deleted.update({"site_id": site_id}) or True,
    )
    monkeypatch.setattr(
        routes_grid,
        "save_grid_official_evidence",
        lambda site_id, payload: saved.update({"site_id": site_id, "payload": payload}),
    )

    evidence = GridOfficialEvidence(
        utility_or_tso_reference="TSO-REF-123",
        confirmed_voltage_kv=220.0,
    )

    result = asyncio.run(
        routes_grid.save_grid_official_evidence_endpoint("site-evidence-route", evidence)
    )

    assert saved["site_id"] == "site-evidence-route"
    assert saved["payload"]["confirmed_voltage_kv"] == pytest.approx(220.0)
    assert deleted["site_id"] == "site-evidence-route"
    assert result.has_evidence is True
    assert result.evidence is not None
    assert result.evidence.utility_or_tso_reference == "TSO-REF-123"


def test_overpass_provider_normalizes_osm_payload(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "elements": [
                    {
                        "type": "way",
                        "id": 101,
                        "tags": {
                            "power": "line",
                            "name": "Transmission Line 101",
                            "operator": "Terna",
                            "voltage": "132000;220000",
                            "circuits": "1;1",
                        },
                        "geometry": [
                            {"lat": 45.0000, "lon": 9.0000},
                            {"lat": 45.0100, "lon": 9.0200},
                        ],
                    },
                    {
                        "type": "node",
                        "id": 202,
                        "tags": {
                            "power": "substation",
                            "name": "Substation 202",
                            "operator": "DSO",
                            "voltage": "150000",
                        },
                        "lat": 45.0200,
                        "lon": 9.0300,
                    },
                    {
                        "type": "way",
                        "id": 303,
                        "tags": {
                            "power": "substation",
                            "voltage": "220000",
                        },
                        "geometry": [
                            {"lat": 45.0300, "lon": 9.0300},
                            {"lat": 45.0300, "lon": 9.0400},
                            {"lat": 45.0400, "lon": 9.0400},
                            {"lat": 45.0300, "lon": 9.0300},
                        ],
                    },
                ]
            }

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    import requests

    monkeypatch.setattr(requests, "post", fake_post)

    provider = OverpassGridContextProvider(endpoint_url="https://example.com/overpass")
    assets = provider.get_assets(
        site_id="site-5",
        site_name="Real Site",
        latitude=45.0,
        longitude=9.0,
        radius_km=5.0,
    )

    assert captured["url"] == "https://example.com/overpass"
    assert 'around:5000,45.000000,9.000000' in captured["data"]["data"]
    assert 'way["power"~"^(line|minor_line|cable)$"]' in captured["data"]["data"]
    assert "out body geom;" in captured["data"]["data"]
    assert "out body geom center;" in captured["data"]["data"]
    assert len(assets) == 3

    assets_by_id = {asset.asset_id: asset for asset in assets}
    line = assets_by_id["osm-way-101"]
    point_substation = assets_by_id["osm-node-202"]
    polygon_substation = assets_by_id["osm-way-303"]

    assert line.asset_type == "line"
    assert line.voltage_kv == pytest.approx(220.0)
    assert line.circuits == 2
    assert line.geometry_type == "line"
    assert line.source == GRID_CONTEXT_SOURCE_LAYER

    assert point_substation.asset_type == "substation"
    assert point_substation.geometry_type == "point"
    assert point_substation.voltage_kv == pytest.approx(150.0)

    assert polygon_substation.asset_type == "substation"
    assert polygon_substation.geometry_type == "polygon"
    assert polygon_substation.name == "Mapped 220 kV substation"


def test_overpass_provider_skips_line_center_fallback_but_keeps_substation_point(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "elements": [
                    {
                        "type": "way",
                        "id": 404,
                        "tags": {
                            "power": "line",
                            "name": "Center-only line",
                            "voltage": "132000",
                        },
                        "center": {"lat": 45.0000, "lon": 9.0100},
                    },
                    {
                        "type": "node",
                        "id": 505,
                        "tags": {
                            "power": "substation",
                            "name": "Point substation",
                            "voltage": "220000",
                        },
                        "lat": 45.0200,
                        "lon": 9.0300,
                    },
                ]
            }

    def fake_post(url, data=None, headers=None, timeout=None):
        del url, data, headers, timeout
        return FakeResponse()

    import requests

    monkeypatch.setattr(requests, "post", fake_post)

    provider = OverpassGridContextProvider(endpoint_url="https://example.com/overpass")
    assets = provider.get_assets(
        site_id="site-geometry-strict",
        site_name="Geometry Strict Site",
        latitude=45.0,
        longitude=9.0,
        radius_km=5.0,
    )

    assert [asset.asset_id for asset in assets] == ["osm-node-505"]
    assert assets[0].asset_type == "substation"
    assert assets[0].geometry_type == "point"


def test_fetch_grid_context_route_surfaces_provider_errors(monkeypatch):
    class FailingProvider:
        def get_assets(self, **kwargs):
            del kwargs
            raise GridContextProviderError("Grid Context could not reach the mapped-public asset service.")

    site = _site_with_coordinates()
    monkeypatch.setattr(routes_grid, "get_site", lambda site_id: (site_id, site))
    monkeypatch.setattr(routes_grid, "get_grid_context", lambda site_id, radius_key: None)
    monkeypatch.setattr(routes_grid, "get_default_grid_context_provider", lambda: FailingProvider())

    request = GridContextRequest(site_id="site-6", radius_km=5.0)

    with pytest.raises(routes_grid.HTTPException) as excinfo:
        asyncio.run(routes_grid.fetch_grid_context_endpoint(request))

    assert excinfo.value.status_code == 502
    assert "mapped-public asset service" in excinfo.value.detail
