# Deploying Quintal for Malia

Goal: Malia opens a private URL on her laptop or phone — no install — and her 👍/👎 land
in the same shared store as yours. Hosted on **Streamlit Community Cloud** (free).

## How it fits together
- **Code** lives on `main` (runtime data stays gitignored, per the project's design).
- **Data** (listings, enrichment cache, photos) is carried on a **`deploy` branch** that
  Streamlit Cloud tracks. You refresh it with `scripts/publish.sh` after each collection.
- **Preferences** (the 👍/👎/hide + area sentiment) live in a **private GitHub Gist** —
  durable (Streamlit's disk is ephemeral) and shared live between you two. Configured via
  two secrets; when they're absent the app falls back to the local `data/preferences.json`.

## One-time setup

### 1. GitHub repo + remote
```bash
gh repo create Xidorian/Quintal --private --source=. --remote=origin --push
```

### 2. Shared preferences Gist
1. Create a **secret** Gist at <https://gist.github.com> with one file named
   `preferences.json` and content `{}`. Copy its id from the URL
   (`gist.github.com/<user>/<THIS_IS_THE_ID>`).
2. Create a **fine-grained** token at
   <https://github.com/settings/personal-access-tokens/new>: no repo access needed, set
   **Account permissions → Gists → Read and write**. Copy it.
3. Seed the Gist with your current preferences:
   ```bash
   . .venv/bin/activate
   QUINTAL_GIST_ID=<id> QUINTAL_GITHUB_TOKEN=<token> python -m quintal.seed_prefs
   ```

### 3. Publish the data
```bash
scripts/publish.sh          # pushes a data snapshot to the `deploy` branch
```

### 4. Create the Streamlit Cloud app
1. Go to <https://share.streamlit.io> → sign in with GitHub → **Create app**.
2. Repo `Xidorian/Quintal`, **branch `deploy`**, main file `app.py`.
3. **Advanced → Secrets** — paste (see `.streamlit/secrets.toml.example`):
   ```toml
   QUINTAL_GIST_ID = "<id>"
   QUINTAL_GITHUB_TOKEN = "<token>"
   ```
4. Deploy. Once up, **Settings → Sharing** → set to specific viewers and add Malia's
   Google/GitHub email. Send her the URL.

## Routine: after collecting new listings
```bash
# (collect + enrich + photos as usual, then)
scripts/publish.sh          # Streamlit Cloud redeploys from `deploy` within a minute
```

## Notes & caveats
- **Cold start:** the free tier sleeps idle apps; first hit after a nap takes ~30 s to wake.
- **Shared writes** are last-write-wins — fine for two people; each click re-reads the Gist
  first, so the clobber window is tiny.
- **Token is a secret:** it lives only in Streamlit's Secrets box / your local env, never in
  the repo. `.streamlit/secrets.toml` is gitignored. Scope it to Gists-only so a leak can't
  touch anything else; rotate it if it's ever exposed.
- **Photos** (~20 MB) ship on `deploy` so thumbnails render. If that branch ever feels heavy,
  they're re-fetchable and can be dropped from `publish.sh`.
