"""Suite-wide guard: a test can never reach the shared preferences store.

`preferences.default_backend()` picks the Gist whenever QUINTAL_GIST_ID and
QUINTAL_GITHUB_TOKEN are in the environment, and `feedback._load_prefs()` calls
`load_dotenv()` at call time — so once those keys exist in a developer's .env, running
pytest talks to the LIVE store that both searchers write from. `feedback.main(["block"])`
and `["resolve"]` save, which is a write to Malia's real preferences.

This is not hypothetical. The keys landed in .env on 2026-10-04 and
test_cli_report_block_resolve_round_trip immediately read 45 live notes instead of its own
fixture. It happened to assert-fail on the report before reaching its block/resolve calls,
so nothing was written (confirmed against the Gist's revision history: last write
2026-09-30T10:37:30Z, no resolved or retracted entries). That was luck.

The test already did `monkeypatch.delenv` on both keys. It wasn't enough, and that is the
lesson worth keeping: the delenv ran at setup, and the `load_dotenv()` inside the function
under test put them straight back. Env hygiene in one test cannot survive a call that
re-reads .env, so the guard belongs here, once, for every test present and future.

Two layers, because the first is a policy and the second is a tripwire:
  1. the keys are removed and `load_dotenv` is neutered, so `default_backend()` falls back
     to the local file the way the tests assume;
  2. `GistBackend.save` raises, so if any test ever does reach a real backend it fails
     loudly instead of silently writing to the live store.

alarm-proved 2026-10-04, each layer separately, because one proof does not cover the other:
  · layer 1 — disabled in place, test_cli_report_block_resolve_round_trip went red reading
    45 live notes instead of its own single fixture row;
  · layer 2 — a throwaway test calling `GistBackend("gid","tok").save({...})` raised, and
    was deleted. Worth noting *why* it needed its own proof: with layer 1 off, the
    round-trip test still fails on its report assertion before it ever reaches `resolve`,
    so it never exercises the tripwire. The first proof looked like it covered both.
"""

from __future__ import annotations

import dotenv
import pytest

from quintal.preferences import GistBackend

SHARED_STORE_ENV = ("QUINTAL_GIST_ID", "QUINTAL_GITHUB_TOKEN")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "exercises_gist_backend: this test drives GistBackend itself against a fake "
        "requests module, so the save tripwire is lifted for it.",
    )


@pytest.fixture(autouse=True)
def never_touch_the_shared_store(monkeypatch, request):
    for key in SHARED_STORE_ENV:
        monkeypatch.delenv(key, raising=False)

    # `from dotenv import load_dotenv` inside a function resolves this attribute at call
    # time, so patching it here covers every entry point that loads .env mid-call.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)

    # The tripwire would otherwise block the tests of GistBackend.save itself, which drive
    # it against a fake `requests` and never open a socket. They say so with a marker, so
    # the exemption is one grep away rather than a hole nobody can see.
    if request.node.get_closest_marker("exercises_gist_backend"):
        return

    def _refuse(self, payload):  # noqa: ARG001 — signature must match
        raise AssertionError(
            "a test tried to WRITE to the shared preferences Gist. "
            "Pass an explicit local backend, or a tmp_path, instead."
        )

    monkeypatch.setattr(GistBackend, "save", _refuse)
