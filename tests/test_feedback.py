"""The 👎-with-a-reason loop: log → report → mined patterns → hard block."""

import json

import pytest

from quintal import feedback
from quintal.preferences import Preferences
from quintal.schema import Listing
from quintal.screening import Blocklist


def _pool(tmp_path, rows, descriptions=None):
    listings = tmp_path / "listings.jsonl"
    listings.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )
    desc = tmp_path / "descriptions.json"
    desc.write_text(json.dumps(descriptions or {}), encoding="utf-8")
    return {
        "region": "algarve",
        "listings": str(listings),
        "blocklist_path": str(tmp_path / "blocklist.json"),
        "descriptions_path": str(desc),
    }


def _row(url, title, text=""):
    return {"source_url": url, "title": title, "description_raw": text, "price_eur_month": 900}


# --- The log ------------------------------------------------------------------


def test_dislike_with_a_reason_logs_why(tmp_path):
    p = Preferences(tmp_path / "prefs.json")
    p.dislike(
        "abc", reason="seasonal", note="só até junho", by="Malia", context={"pool": "Algarve"}
    )

    entry = p.latest_feedback("abc")
    assert entry["reason"] == "seasonal"
    assert entry["note"] == "só até junho"
    assert entry["by"] == "Malia"
    assert entry["pool"] == "Algarve"
    assert entry["at"] and entry["entry_id"]


def test_plain_dislike_still_toggles_and_logs_nothing(tmp_path):
    p = Preferences(tmp_path / "prefs.json")
    p.dislike("abc")
    assert p.listing_state("abc") == "disliked"
    assert p.feedback == []


def test_un_passing_retracts_the_note(tmp_path):
    p = Preferences(tmp_path / "prefs.json")
    p.dislike("abc", reason="seasonal", note="wrong call")
    p.dislike("abc")  # toggles the 👎 back off

    assert p.listing_state("abc") == "neutral"
    assert p.feedback[0]["retracted"] is True
    assert p.open_feedback() == []  # a reversed 👎 can't drive a filter change
    assert p.latest_feedback("abc") is None


def test_feedback_survives_a_roundtrip(tmp_path):
    path = tmp_path / "prefs.json"
    p = Preferences(path)
    p.dislike("abc", reason="gone", note="already rented")
    p.save()

    assert Preferences(path).latest_feedback("abc")["reason"] == "gone"


def test_old_payload_without_a_log_loads(tmp_path):
    path = tmp_path / "prefs.json"
    path.write_text(json.dumps({"liked": ["a"], "disliked": [], "hidden": [], "areas": {}}))
    p = Preferences(path)
    assert p.feedback == []
    assert p.listing_state("a") == "liked"


def test_resolve_closes_entries(tmp_path):
    p = Preferences(tmp_path / "prefs.json")
    p.dislike("abc", reason="seasonal", note="x")
    entry_id = p.feedback[0]["entry_id"]

    assert p.resolve_feedback([entry_id], note="QT-044 pattern added") == 1
    assert p.open_feedback() == []
    assert p.feedback[0]["resolution"] == "QT-044 pattern added"
    assert p.resolve_feedback([entry_id]) == 0  # already closed, not double-counted


# --- Joining back to the listing text -----------------------------------------


def test_corpus_id_matches_the_pipeline_listing_id():
    """The report joins the log to store rows by id — it must be the *same* id."""
    url = "https://www.imovirtual.com/pt/anuncio/xyz"
    assert feedback._id_for_url(url) == Listing(price_eur_month=1, source_url=url).ensure_id()


def test_load_corpus_prefers_the_detail_description(tmp_path):
    pool = _pool(
        tmp_path,
        [_row("https://x/1", "T2 em Faro", "card preview")],
        descriptions={"https://x/1": "texto completo do anúncio"},
    )
    corpus = feedback.load_corpus(pool)
    entry = corpus[feedback._id_for_url("https://x/1")]
    assert "texto completo" in entry["text"]
    assert entry["title"] == "T2 em Faro"


# --- The report ---------------------------------------------------------------


def test_report_separates_still_slipping_from_now_caught(tmp_path):
    pool = _pool(
        tmp_path,
        [
            _row("https://x/1", "T2 Lagos", "arrendamento apenas na época escolar"),
            _row("https://x/2", "T3 Faro", "arrendamento para ferias, por semana"),
        ],
    )
    p = Preferences(tmp_path / "prefs.json")
    p.dislike(feedback._id_for_url("https://x/1"), reason="seasonal", note="época escolar")
    p.dislike(feedback._id_for_url("https://x/2"), reason="seasonal", note="férias")

    report = feedback.build_report(p, "Algarve", pool)
    verdicts = {f.listing_id: f.caught_by for f in report.findings}
    assert verdicts[feedback._id_for_url("https://x/1")] is None  # no pattern covers it yet
    assert "matched" in verdicts[feedback._id_for_url("https://x/2")]  # the screener owns it


def test_report_splits_taste_from_filter_misses(tmp_path):
    pool = _pool(tmp_path, [_row("https://x/1", "T2 Lagos", "casa bonita")])
    p = Preferences(tmp_path / "prefs.json")
    p.dislike("a", reason="location", note="too far", context={"concelho": "Portimão"})
    p.dislike("b", reason="price", note="não vale")
    p.dislike(feedback._id_for_url("https://x/1"), reason="duplicate")

    report = feedback.build_report(p, "Algarve", pool)
    assert [f.reason for f in report.findings] == ["duplicate"]
    assert {t["reason"] for t in report.taste} == {"location", "price"}
    assert report.taste[0]["places"] or report.taste[1]["places"]


def test_report_ignores_the_other_pool(tmp_path):
    pool = _pool(tmp_path, [_row("https://x/1", "T2 Lagos")])
    p = Preferences(tmp_path / "prefs.json")
    p.dislike("a", reason="seasonal", context={"pool": "Norte — Porto · Douro · Minho"})
    assert feedback.build_report(p, "Algarve", pool).findings == []


def test_render_report_runs_on_an_empty_log(tmp_path):
    pool = _pool(tmp_path, [_row("https://x/1", "T2 Lagos")])
    report = feedback.build_report(Preferences(tmp_path / "p.json"), "Algarve", pool)
    text = feedback.render_report(report)
    assert "No open filter misses" in text


# --- Pattern mining -----------------------------------------------------------


def test_mining_proposes_a_phrase_shared_by_the_missed_listings(tmp_path):
    corpus = {
        "keep1": {"title": "T2 anual", "text": "arrendamento anual em Faro", "url": ""},
        "keep2": {"title": "T3 anual", "text": "contrato de um ano", "url": ""},
    }
    missed = [
        "disponivel apenas para epoca escolar setembro",
        "arrendamento epoca escolar, estudantes",
    ]
    phrases = [c.phrase for c in feedback.mine_patterns(missed, corpus)]
    assert "epoca escolar" in phrases


def test_a_single_missed_listing_only_yields_what_the_note_quoted():
    corpus = {"keep": {"title": "x", "text": "arrendamento anual", "url": ""}}
    missed = ["moradia na rua do sol 14, disponivel so na epoca escolar"]

    silent = feedback.mine_patterns(missed, corpus)
    assert silent == []  # one listing's n-grams are mostly its own address

    quoted = feedback.mine_patterns(missed, corpus, notes=["diz epoca escolar"])
    assert [c.phrase for c in quoted] == ["epoca escolar"]
    assert quoted[0].quoted is True


def test_mining_drops_phrases_a_shorter_one_already_covers():
    corpus = {"keep": {"title": "x", "text": "arrendamento anual", "url": ""}}
    missed = ["disponivel para o ano letivo apenas", "so para o ano letivo, professores"]
    phrases = [c.phrase for c in feedback.mine_patterns(missed, corpus)]
    assert "ano letivo" in phrases
    assert "o ano letivo" not in phrases  # subsumed by the shorter, equally effective phrase


def test_mining_reports_collateral_and_skips_generic_phrases():
    corpus = {
        f"k{i}": {"title": f"T2 #{i}", "text": "moradia com quintal em Faro", "url": ""}
        for i in range(50)
    }
    corpus["k0"]["text"] = "moradia com quintal em Faro epoca escolar"
    missed = ["moradia com quintal epoca escolar", "epoca escolar moradia com quintal"]

    by_phrase = {c.phrase: c for c in feedback.mine_patterns(missed, corpus)}
    assert by_phrase["epoca escolar"].collateral == 1  # only k0 would also be purged
    assert "moradia com quintal" not in by_phrase  # in 50/50 of the pool — far too generic


def test_mining_skips_what_the_screener_already_catches():
    corpus = {"keep": {"title": "x", "text": "arrendamento anual", "url": ""}}
    missed = ["arrendamento para ferias na praia", "casa para ferias em agosto"]
    assert not any(
        "ferias" in c.phrase for c in feedback.mine_patterns(missed, corpus)
    )  # "para ferias" is already a SHORT_TERM_PATTERN


def test_mining_returns_nothing_without_text():
    assert feedback.mine_patterns([], {}) == []


# --- Hard-blocking ------------------------------------------------------------


def test_block_writes_the_offenders_into_the_blocklist(tmp_path):
    pool = _pool(tmp_path, [_row("https://x/1", "T2 Lagos", "época escolar")])
    lid = feedback._id_for_url("https://x/1")
    p = Preferences(tmp_path / "prefs.json")
    p.dislike(lid, reason="seasonal", note="só até junho", by="Malia")
    p.dislike("taste-only", reason="price", note="caro")

    blocked = feedback.block_open_findings(p, "Algarve", pool)

    assert [e["listing_id"] for e in blocked] == [lid]  # taste never blocks
    entries = Blocklist(pool["blocklist_path"]).entries
    assert lid in entries
    assert "feedback:seasonal" in entries[lid] and "só até junho" in entries[lid]
    assert p.latest_feedback(lid)["blocked_at"]


def test_block_is_idempotent(tmp_path):
    pool = _pool(tmp_path, [_row("https://x/1", "T2 Lagos")])
    lid = feedback._id_for_url("https://x/1")
    p = Preferences(tmp_path / "prefs.json")
    p.dislike(lid, reason="gone")

    feedback.block_open_findings(p, "Algarve", pool)
    assert feedback.block_open_findings(p, "Algarve", pool) == []


def test_block_dry_run_writes_nothing(tmp_path):
    pool = _pool(tmp_path, [_row("https://x/1", "T2 Lagos")])
    lid = feedback._id_for_url("https://x/1")
    p = Preferences(tmp_path / "prefs.json")
    p.dislike(lid, reason="gone")

    assert feedback.block_open_findings(p, "Algarve", pool, dry_run=True)
    assert not (tmp_path / "blocklist.json").exists()
    assert "blocked_at" not in p.latest_feedback(lid)


# --- Taxonomy -----------------------------------------------------------------


def test_every_screenable_reason_names_where_the_fix_belongs():
    for code in feedback.SCREENABLE:
        assert feedback.REASONS[code].target


def test_unknown_reason_code_falls_back_to_its_own_label():
    assert feedback.label_of("nonsense") == "nonsense"


def test_context_from_view_snapshots_the_card():
    view = {"title": "T2", "url": "https://x/1", "concelho": "Faro", "price": 900.0}
    ctx = feedback.context_from_view(view, "Algarve")
    assert ctx == {
        "pool": "Algarve",
        "title": "T2",
        "url": "https://x/1",
        "concelho": "Faro",
        "price": 900.0,
    }


# --- CLI ----------------------------------------------------------------------


def test_cli_report_block_resolve_round_trip(tmp_path, monkeypatch, capsys):
    pool = _pool(tmp_path, [_row("https://x/1", "T2 Lagos", "época escolar apenas")])
    monkeypatch.setattr(feedback.config, "POOLS", {"Algarve": pool}, raising=True)
    monkeypatch.delenv("QUINTAL_GIST_ID", raising=False)
    monkeypatch.delenv("QUINTAL_GITHUB_TOKEN", raising=False)
    prefs_path = str(tmp_path / "prefs.json")

    p = Preferences(prefs_path)
    p.dislike(feedback._id_for_url("https://x/1"), reason="seasonal", note="só até junho")
    p.save()

    assert feedback.main(["report", "--pool", "algarve", "--prefs", prefs_path]) == 0
    assert "still slips" in capsys.readouterr().out

    assert feedback.main(["block", "--pool", "algarve", "--prefs", prefs_path]) == 0
    assert "blocked 1 listing" in capsys.readouterr().out

    assert feedback.main(["resolve", "--all", "--pool", "algarve", "--prefs", prefs_path]) == 0
    assert "resolved 1" in capsys.readouterr().out
    assert Preferences(prefs_path).open_feedback() == []


def test_cli_report_json_is_machine_readable(tmp_path, monkeypatch, capsys):
    pool = _pool(tmp_path, [_row("https://x/1", "T2 Lagos", "época escolar apenas")])
    monkeypatch.setattr(feedback.config, "POOLS", {"Algarve": pool}, raising=True)
    prefs_path = str(tmp_path / "prefs.json")
    p = Preferences(prefs_path)
    p.dislike(feedback._id_for_url("https://x/1"), reason="seasonal")
    p.save()

    feedback.main(["report", "--pool", "algarve", "--prefs", prefs_path, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["findings"][0]["reason"] == "seasonal"
    assert payload["findings"][0]["target"]


def test_cli_rejects_an_unknown_pool(tmp_path):
    with pytest.raises(KeyError):
        feedback.main(["report", "--pool", "atlantis"])
