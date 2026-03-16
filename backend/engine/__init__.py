"""
DC Feasibility Tool v4 — Engine Package

This package contains all calculation logic. It has ZERO UI dependencies.
You can import and use any module here from a Python script or test
without starting the server.

Modules (will be built in Phases 1-3):
    models.py       — Pydantic data models (Site, Scenario, Result)
    assumptions.py  — All defaults with source citations
    space.py        — Site geometry calculations
    power.py        — Power chain, redundancy, procurement
    cooling.py      — COP model, cooling modes, hourly cooling load
    pue_engine.py   — Hourly 8760 PUE simulation
    climate.py      — Climate analysis and suitability
    weather.py      — Open-Meteo fetch, KML parse, geocoding
    footprint.py    — Infrastructure area calculations
    expansion.py    — Advisory-only future build-out potential
    ranking.py      — RAG status, scoring, load mix optimizer
    sensitivity.py  — Tornado chart, break-even analysis
    backup_power.py — Genset, fuel cell, hydrogen alternatives
    green_energy.py — PV, BESS, fuel cell dispatch
"""
