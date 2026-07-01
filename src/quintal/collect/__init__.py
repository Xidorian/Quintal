"""Phase 2 — browser-session collection.

Collection is done by driving the searcher's own logged-in Chrome (ToS-respecting,
no anti-bot infra). The fragile part — pulling listing cards out of a rendered results
page — happens at runtime via the browser tools and yields `ExtractedRow` dicts. The
durable, tested part lives here: parsing PT number/area/typology formats, mapping each
extracted row into the canonical raw listing dict, and persisting idempotently to
`data/listings.jsonl`.
"""
