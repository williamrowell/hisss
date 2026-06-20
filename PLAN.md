# hisss — a simple Python notification wrapper for the brrr API

## Context

You want a small, ergonomic Python wrapper around the [brrr](https://brrr.now/docs)
push-notification API so that sending a notification is a single function call
(plus a CLI for ad-hoc use). The current draft uses `urllib`, hard-codes a couple
of fields, omits most parameters, and has no auth. The goal is a clean
`send(...)` function that supports **all** brrr parameters, takes the auth token
from the environment (never hard-coded or committed), and is easy to run.

Decisions locked in from our Q&A:
- **HTTP:** `requests`.
- **Shape:** one self-contained script `hisss.py` using **PEP 723** inline
  dependency metadata, runnable with `uv`/`uvx`; **tests embedded in the same file**.
- **Tooling:** `ruff` (lint + format), `ty` (type check) — both via `uvx`.
- **Secrets:** **env var only** — token read from `BRRR_TOKEN`.

Environment confirmed: Python 3.12.3, `uv` 0.10.9, `git` 2.43. `ruff`/`ty` run
on demand through `uvx` (not installed standalone, which is fine).

## Deliverable: files

```
hisss/
├── hisss.py        # the whole thing: send(), CLI, embedded tests, PEP 723 header
├── README.md       # usage, token setup, uv/ruff/ty commands, security notes
├── ruff.toml       # lint/format config (line length, rule selection)
├── .gitignore      # .env, __pycache__/, .venv/, .ruff_cache/, .pytest_cache/, *.pyc
└── PLAN.md         # a copy of this plan (committed in the first commit)
```

No `pyproject.toml` — dependencies live in the PEP 723 header so the script stays
standalone and `uv`-runnable.

## `hisss.py` design

### PEP 723 header + shebang
```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["requests"]
# ///
```
This makes `./hisss.py ...` (or `uv run hisss.py ...`) auto-provision `requests`
in an ephemeral env — no manual install.

### Constants & validation tables
- `DEFAULT_BASE_URL = "https://api.brrr.now/v1/send"`
- `SOUNDS: frozenset[str]` — the documented sound names (default, system, brrr,
  bell_ringing, … warm_soft_error).
- `INTERRUPTION_LEVELS: frozenset[str]` — passive, active, time-sensitive, critical.

### Exceptions
- `HisssError(Exception)` — base.
- `HisssAuthError(HisssError)` — no token resolved.
- `HisssAPIError(HisssError)` — non-2xx; stores `status` and response `body`.
  **The token is never included in any exception message or log** (Authorization
  header is redacted).

### Token resolution
```python
def _resolve_token(token: str | None) -> str:
    # explicit arg  ->  BRRR_TOKEN env  ->  raise HisssAuthError
```
Token is never written to disk by the library and never logged.

### Core function — all brrr parameters
```python
def send(
    message: str | None = None,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    thread_id: str | None = None,
    sound: str | None = None,
    volume: float | None = None,
    open_url: str | None = None,
    image_url: str | None = None,
    expiration_date: str | datetime | None = None,
    filter_criteria: str | None = None,
    interruption_level: str | None = None,
    token: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = 10.0,
    session: requests.Session | None = None,
) -> dict:
```
Behavior:
- Require at least one of `title` / `message`.
- **Omit `None` fields** from the JSON body (the original curl sends empty strings
  for everything — we won't).
- Validate `sound` against `SOUNDS` and `interruption_level` against
  `INTERRUPTION_LEVELS` when provided; validate `volume` is a float in `[0, 1]`.
- `expiration_date`: accept a `datetime` and serialize to brrr's
  `YYYY-MM-DDTHH:MM:SS.000Z` (UTC), or pass a string through unchanged.
- POST with header `Authorization: Bearer <token>` and `Content-Type: application/json`.
- Raise `HisssAPIError` on non-2xx (redacted); return parsed JSON (`{}` if empty body).

### CLI
`main(argv)` via `argparse`: positional `message`, a flag per parameter
(`--title`, `--sound`, `--interruption-level`, `--volume`, `--open-url`, …),
`--token` optional (falls back to `BRRR_TOKEN`). Prints the API response;
exits non-zero with a clean redacted message on failure.
`if __name__ == "__main__": sys.exit(main(sys.argv[1:]))`.

### Embedded tests
Pytest-style `def test_*` functions in the same file, using stdlib
`unittest.mock` to patch `requests.Session.request` / `requests.post` — **no
network, no extra mock dependency.** Coverage:
- payload omits `None` fields and includes only what was passed;
- `Authorization: Bearer` header set from arg and from `BRRR_TOKEN`;
- missing token raises `HisssAuthError`;
- `volume` out of range / unknown `sound` / unknown `interruption_level` raise;
- `datetime` → ISO8601 `…Z` serialization;
- non-2xx raises `HisssAPIError` with status, token **not** present in the message.

## Token security (env var only)

- The token lives only in `BRRR_TOKEN` in the environment — never in source,
  never committed. `.gitignore` excludes `.env`.
- Recommended ways to set it without leaking into shell history:
  - a gitignored `.env` you `source` (or `set -a; . ./.env; set +a`), or
  - one-shot inline: `BRRR_TOKEN=… uv run hisss.py "msg"`, or
  - `read -rs BRRR_TOKEN && export BRRR_TOKEN`.
- The provided test token is used **only** via the environment at test time and is
  never written into any file. You'll rotate it afterward.
- The library redacts the token from all errors/logs.

## Verification

Run from the repo root:
```bash
# Lint, format-check, type-check
uvx ruff check hisss.py
uvx ruff format --check hisss.py
uvx ty check hisss.py

# Embedded unit tests (no network)
uvx --with requests --with pytest pytest hisss.py -q

# Live smoke test (sends a real notification; token via env, then rotate)
BRRR_TOKEN=br_usr_… uv run hisss.py "Hello from hisss 🐍" \
  --title hisss --sound brrr --interruption-level active
```
Expect ruff/ty clean, all embedded tests passing, and the live call returning a
2xx with a real push arriving on your device.

## Git plan

1. `git init` (currently not a repo).
2. Copy this plan to `PLAN.md`.
3. **First commit = the plan only** (`PLAN.md`), per your request.
4. Implement `hisss.py`, `README.md`, `ruff.toml`, `.gitignore`; run the
   verification suite; then a second commit with the working implementation.
5. No pushing/remote unless you ask.
