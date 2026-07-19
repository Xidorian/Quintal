"""One-time: copy the local `data/preferences.json` into the shared Gist.

Run once, after creating the private Gist + token, to carry existing 👍/👎 across:

    QUINTAL_GIST_ID=... QUINTAL_GITHUB_TOKEN=... python -m quintal.seed_prefs

Reads env only (never hardcode the token). Refuses to overwrite a Gist that already
holds preferences unless `--force` is given, so a re-run can't wipe live sentiment.
"""

from __future__ import annotations

import argparse
import os
import sys

from quintal.preferences import GistBackend, LocalFileBackend

LOCAL_PATH = "data/preferences.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the shared preferences Gist from local.")
    parser.add_argument("--path", default=LOCAL_PATH, help="local preferences file to upload")
    parser.add_argument(
        "--force", action="store_true", help="overwrite even if the Gist already has data"
    )
    args = parser.parse_args(argv)

    gist_id = os.getenv("QUINTAL_GIST_ID")
    token = os.getenv("QUINTAL_GITHUB_TOKEN")
    if not (gist_id and token):
        print("Set QUINTAL_GIST_ID and QUINTAL_GITHUB_TOKEN first.", file=sys.stderr)
        return 2

    local = LocalFileBackend(args.path).load()
    if not local:
        print(f"No local preferences at {args.path} — nothing to seed.", file=sys.stderr)
        return 1

    gist = GistBackend(gist_id, token)
    existing = gist.load()
    if existing and any(existing.get(k) for k in ("liked", "disliked", "hidden", "areas")):
        if not args.force:
            print(
                "Gist already holds preferences; refusing to overwrite. Re-run with --force.",
                file=sys.stderr,
            )
            return 1

    gist.save(local)
    counts = {k: len(local.get(k, [])) for k in ("liked", "disliked", "hidden", "areas")}
    print(f"Seeded Gist {gist_id} from {args.path}: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
