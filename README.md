# hisss 🐍

<img src="assets/logo.svg" alt="hisss" height="64">

A tiny, single-file Python wrapper around the [brrr](https://brrr.now/docs) push-notification API.

> hisss is an unofficial client and is not affiliated with or endorsed by brrr.
One function, every brrr parameter, zero install friction (deps are declared
inline via [PEP 723](https://peps.python.org/pep-0723/) and provisioned by
[`uv`](https://docs.astral.sh/uv/)).

## Quick start

```python
import hisss

hisss.send("Build finished ✅", title="CI", sound="brrr")
```

From the command line (the shebang runs it through `uv`, auto-installing `requests`):

```bash
export BRRR_TOKEN=br_usr_…
./hisss.py "Hello from hisss" --title hisss --sound brrr --interruption-level active
```

or explicitly:

```bash
uv run hisss.py "Hello" --title hisss
```

## The token (read from the environment)

hisss reads the auth token from the **`BRRR_TOKEN`** environment variable, or you
can pass `token=...` / `--token`. It is **never** hard-coded, written to disk, or
logged — the `Authorization` header is redacted from every error.

Set it without leaking into shell history:

```bash
# one-shot, inline (not stored)
BRRR_TOKEN=br_usr_… ./hisss.py "ping"

# prompt without echo
read -rs BRRR_TOKEN && export BRRR_TOKEN

# or a gitignored .env you source
set -a; . ./.env; set +a
```

`.env` is gitignored — keep your token there if you like, but never commit it.

## `send()` parameters

`message` is positional; everything else is keyword-only.

| Parameter | Notes |
|---|---|
| `message` | Body text. At least one of `message`/`title` is required. |
| `title`, `subtitle` | Heading text. |
| `thread_id` | Group related notifications. |
| `sound` | One of the documented sounds (`default`, `system`, `brrr`, `bell_ringing`, …). |
| `volume` | Float `0–1`, critical interruption level only. |
| `open_url` | URL opened when the notification is tapped. |
| `image_url` | Image to display. |
| `expiration_date` | ISO8601 string **or** a `datetime` (serialized to UTC `…Z`). |
| `filter_criteria` | Focus filter name (`work`, `sleep`, `deep work`, …). |
| `interruption_level` | `passive`, `active`, `time-sensitive`, or `critical`. |
| `token` | Defaults to `BRRR_TOKEN`. |
| `base_url`, `timeout`, `session` | Endpoint override, per-request timeout, optional `requests.Session`. |

Unset (`None`) fields are omitted from the request body. Invalid `sound`,
`interruption_level`, or out-of-range `volume` raise `HisssError` before any
network call.

## Development

```bash
# lint, format-check, type-check
uvx ruff check hisss.py
uvx ruff format --check hisss.py
uvx --with requests --with pytest ty check hisss.py

# embedded unit tests (no network)
uvx --with requests --with pytest pytest hisss.py -q
```

The tests live in `hisss.py` itself and mock `requests` — they never hit the network.

## License

[MIT-0](LICENSE) (MIT No Attribution) — do whatever you like, no attribution required.
