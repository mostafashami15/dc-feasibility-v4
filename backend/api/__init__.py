"""
DC Feasibility Tool v4 — API Layer
====================================
FastAPI route modules that wrap the engine for the React frontend.

Phase 4 of the Architecture Agreement (Section 8).

Files:
    store.py           — JSON file-backed site and weather storage
    routes_site.py     — Site CRUD, KML upload, geocoding (Page 1)
    routes_scenario.py — Scenario execution, scoring, sensitivity (Pages 3–4)
    routes_climate.py  — Weather fetch, climate analysis (Page 2)
    routes_green.py    — Green energy dispatch simulation (Page 5)
    routes_export.py   — Report generation stubs (Page 6, Phase 7)

Design principles:
    1. Zero business logic — all computation lives in engine/
    2. Pydantic request/response models for validation
    3. Stateless endpoints — no server-side session state
    4. Simple JSON responses for easy React consumption
"""
