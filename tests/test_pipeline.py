"""The pipeline CLI's pool wiring.

Same class of bug as QT-047 (the cull writing to the default delisted sidecar), in the
other entry point: `pipeline.main()` passed no sidecar paths at all, so every `run()`
default applied no matter what `--region` said. `--region norte` therefore wrote its
short-term hits into the *Algarve* blocklist, screened against the Algarve delisted set,
and with `--enrich` would have overwritten data/geo.json with Norte coordinates.

Found 2026-09-30 by running the Norte pipeline and watching 714 Norte listings land in
data/blocklist.json. The app never had the bug — it resolves sidecars from `config.POOLS` —
so the fix is to make the CLI do exactly what the app does, and this pins it there.

alarm-proved 2026-09-30 — the fix reverted in place, 3 of these 4 went red.
"""

from __future__ import annotations

import sys

import pytest

from quintal import config, pipeline

SIDECARS = ("blocklist_path", "delisted_path", "geo_path", "cache_path", "descriptions_path")


@pytest.fixture
def captured_run(monkeypatch):
    """Run `main()` without touching disk, returning the kwargs it handed `run()`."""
    seen: dict = {}

    def fake_run(input_path, html_out=None, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(pipeline, "run", fake_run)

    def invoke(*argv: str) -> dict:
        monkeypatch.setattr(sys, "argv", ["quintal.pipeline", *argv])
        pipeline.main()
        return seen

    return invoke


@pytest.mark.parametrize("region", ["algarve", "norte"])
def test_cli_passes_its_own_pools_sidecars(captured_run, region):
    kwargs = captured_run("--input", "data/x.jsonl", "--region", region)
    pool = config.pool_by_region(region)
    for key in SIDECARS:
        assert kwargs[key] == pool[key], f"{region}: {key} must come from its own pool"


def test_norte_cli_shares_no_sidecar_with_algarve(captured_run):
    """The behavioural half: a Norte run must not be able to write an Algarve file."""
    norte = captured_run("--input", "data/listings-norte.jsonl", "--region", "norte")
    algarve = config.pool_by_region("algarve")
    for key in SIDECARS:
        assert norte[key] != algarve[key], f"a Norte run would have written {algarve[key]}"


def test_unknown_region_is_refused_not_silently_defaulted(captured_run):
    """An unknown slug must fail loudly — defaulting it would aim at the Algarve files."""
    with pytest.raises(KeyError):
        captured_run("--input", "data/x.jsonl", "--region", "centro")
