#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["requests"]
# ///
"""hisss — a tiny Python wrapper around the brrr push-notification API.

Send a notification with a single call::

    import hisss
    hisss.send("Build finished", title="CI", sound="brrr")

Or from the command line (auto-provisions ``requests`` via uv)::

    BRRR_TOKEN=br_usr_… ./hisss.py "Hello" --title hisss --sound brrr

The auth token is read from the ``BRRR_TOKEN`` environment variable (or passed
explicitly). It is never hard-coded, written to disk, or printed — the
``Authorization`` header is redacted from every error message.

Embedded tests live in this same file; run them with::

    uvx --with requests --with pytest pytest hisss.py -q
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime

import requests

__all__ = [
    "send",
    "HisssError",
    "HisssAuthError",
    "HisssAPIError",
    "SOUNDS",
    "INTERRUPTION_LEVELS",
    "DEFAULT_BASE_URL",
]

DEFAULT_BASE_URL = "https://api.brrr.now/v1/send"
TOKEN_ENV_VAR = "BRRR_TOKEN"

# Documented brrr sound names.
SOUNDS: frozenset[str] = frozenset(
    {
        "default",
        "system",
        "brrr",
        "bell_ringing",
        "bubble_ding",
        "bubbly_success_ding",
        "cat_meow",
        "calm1",
        "calm2",
        "cha_ching",
        "dog_barking",
        "door_bell",
        "duck_quack",
        "emergency",
        "short_triple_blink",
        "upbeat_bells",
        "warm_soft_error",
    }
)

# Documented brrr interruption levels.
INTERRUPTION_LEVELS: frozenset[str] = frozenset(
    {"passive", "active", "time-sensitive", "critical"}
)


class HisssError(Exception):
    """Base class for all hisss errors."""


class HisssAuthError(HisssError):
    """Raised when no auth token can be resolved."""


class HisssAPIError(HisssError):
    """Raised when the brrr API returns a non-2xx response.

    The auth token is never included here; only the HTTP status and the
    response body (which comes from the API, not from us) are stored.
    """

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"brrr API returned HTTP {status}: {body or '<empty body>'}")


def _resolve_token(token: str | None) -> str:
    """Resolve the auth token: explicit arg, then ``BRRR_TOKEN`` env var."""
    resolved = token if token is not None else os.environ.get(TOKEN_ENV_VAR)
    if not resolved:
        raise HisssAuthError(
            f"No auth token provided. Pass token=... or set the {TOKEN_ENV_VAR} "
            "environment variable."
        )
    return resolved


def _format_expiration(value: str | datetime) -> str:
    """Serialize an expiration date to brrr's ``YYYY-MM-DDTHH:MM:SS.000Z`` form.

    A ``str`` is passed through unchanged (assumed already ISO8601). A
    ``datetime`` is converted to UTC and formatted with millisecond precision.
    """
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    utc = value.astimezone(UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def _build_payload(
    *,
    title: str | None,
    subtitle: str | None,
    message: str | None,
    thread_id: str | None,
    sound: str | None,
    volume: float | None,
    open_url: str | None,
    image_url: str | None,
    expiration_date: str | datetime | None,
    filter_criteria: str | None,
    interruption_level: str | None,
) -> dict[str, object]:
    """Validate inputs and build the JSON body, omitting unset (None) fields."""
    if title is None and message is None:
        raise HisssError("At least one of `title` or `message` is required.")

    if sound is not None and sound not in SOUNDS:
        raise HisssError(
            f"Unknown sound {sound!r}. Valid sounds: {', '.join(sorted(SOUNDS))}."
        )

    if interruption_level is not None and interruption_level not in INTERRUPTION_LEVELS:
        raise HisssError(
            f"Unknown interruption_level {interruption_level!r}. Valid levels: "
            f"{', '.join(sorted(INTERRUPTION_LEVELS))}."
        )

    if volume is not None and not (0.0 <= float(volume) <= 1.0):
        raise HisssError(f"volume must be a float in [0, 1], got {volume!r}.")

    candidate: dict[str, object | None] = {
        "title": title,
        "subtitle": subtitle,
        "message": message,
        "thread_id": thread_id,
        "sound": sound,
        "volume": float(volume) if volume is not None else None,
        "open_url": open_url,
        "image_url": image_url,
        "expiration_date": (
            _format_expiration(expiration_date) if expiration_date is not None else None
        ),
        "filter_criteria": filter_criteria,
        "interruption_level": interruption_level,
    }
    return {key: value for key, value in candidate.items() if value is not None}


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
) -> dict[str, object]:
    """Send a notification through the brrr API.

    Args:
        message: Notification body. At least one of ``message``/``title`` required.
        title: Notification title.
        subtitle: Notification subtitle.
        thread_id: Group related notifications together.
        sound: One of :data:`SOUNDS`.
        volume: Float in ``[0, 1]`` (critical interruption level only).
        open_url: URL opened when the notification is tapped.
        image_url: URL of an image to display.
        expiration_date: ISO8601 string or a ``datetime`` (serialized to UTC).
        filter_criteria: Focus filter name (e.g. ``"work"``, ``"sleep"``).
        interruption_level: One of :data:`INTERRUPTION_LEVELS`.
        token: Auth token; falls back to the ``BRRR_TOKEN`` env var.
        base_url: API endpoint (override for testing).
        timeout: Per-request timeout in seconds.
        session: Optional ``requests.Session`` to reuse a connection.

    Returns:
        The parsed JSON response (``{}`` if the body is empty).

    Raises:
        HisssAuthError: No token could be resolved.
        HisssError: Invalid arguments.
        HisssAPIError: The API responded with a non-2xx status.
    """
    resolved_token = _resolve_token(token)
    payload = _build_payload(
        title=title,
        subtitle=subtitle,
        message=message,
        thread_id=thread_id,
        sound=sound,
        volume=volume,
        open_url=open_url,
        image_url=image_url,
        expiration_date=expiration_date,
        filter_criteria=filter_criteria,
        interruption_level=interruption_level,
    )
    headers = {
        "Authorization": f"Bearer {resolved_token}",
        "Content-Type": "application/json",
    }

    http = session if session is not None else requests
    try:
        response = http.request(
            "POST", base_url, json=payload, headers=headers, timeout=timeout
        )
    except requests.RequestException as exc:
        # Never let the token leak via a chained exception/repr.
        raise HisssError(f"Request to brrr failed: {exc}") from None

    if not (200 <= response.status_code < 300):
        raise HisssAPIError(response.status_code, response.text)

    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hisss",
        description="Send a push notification via the brrr API.",
    )
    parser.add_argument("message", nargs="?", help="Notification body text.")
    parser.add_argument("--title", help="Notification title.")
    parser.add_argument("--subtitle", help="Notification subtitle.")
    parser.add_argument("--thread-id", help="Group related notifications.")
    parser.add_argument(
        "--sound", choices=sorted(SOUNDS), metavar="SOUND", help="Notification sound."
    )
    parser.add_argument("--volume", type=float, help="Volume 0-1 (critical level only).")
    parser.add_argument("--open-url", help="URL to open when tapped.")
    parser.add_argument("--image-url", help="Image URL to display.")
    parser.add_argument(
        "--expiration-date", help="ISO8601 expiration, e.g. 2026-01-01T00:00:00.000Z."
    )
    parser.add_argument("--filter-criteria", help="Focus filter name.")
    parser.add_argument(
        "--interruption-level",
        choices=sorted(INTERRUPTION_LEVELS),
        metavar="LEVEL",
        help="Interruption level.",
    )
    parser.add_argument(
        "--token",
        help=f"Auth token (defaults to the {TOKEN_ENV_VAR} environment variable).",
    )
    parser.add_argument(
        "--base-url", default=DEFAULT_BASE_URL, help="Override the API endpoint."
    )
    parser.add_argument(
        "--timeout", type=float, default=10.0, help="Request timeout in seconds."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    args = _build_arg_parser().parse_args(argv)
    try:
        result = send(
            args.message,
            title=args.title,
            subtitle=args.subtitle,
            thread_id=args.thread_id,
            sound=args.sound,
            volume=args.volume,
            open_url=args.open_url,
            image_url=args.image_url,
            expiration_date=args.expiration_date,
            filter_criteria=args.filter_criteria,
            interruption_level=args.interruption_level,
            token=args.token,
            base_url=args.base_url,
            timeout=args.timeout,
        )
    except HisssError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(result if result else "sent")
    return 0


# --------------------------------------------------------------------------- #
# Embedded tests — run with:
#   uvx --with requests --with pytest pytest hisss.py -q
# --------------------------------------------------------------------------- #

if "pytest" in sys.modules:  # pragma: no cover - only true under pytest
    from unittest import mock

    import pytest

    class _FakeResponse:
        def __init__(self, status_code=200, json_body=None, text="", content=b"{}"):
            self.status_code = status_code
            self._json = json_body if json_body is not None else {}
            self.text = text
            self.content = content

        def json(self):
            return self._json

    def _capture():
        """Return (mock_request, fake_response) wired so send() uses the mock."""
        fake = _FakeResponse(json_body={"ok": True})
        m = mock.Mock(return_value=fake)
        return m, fake

    def test_payload_omits_none_fields():
        m, _ = _capture()
        with mock.patch("requests.request", m):
            send("hello", title="hi", token="t")
        _, kwargs = m.call_args
        assert kwargs["json"] == {"title": "hi", "message": "hello"}

    def test_only_passed_fields_present():
        m, _ = _capture()
        with mock.patch("requests.request", m):
            send("body", title="t", sound="brrr", thread_id="grp", token="t")
        assert m.call_args.kwargs["json"] == {
            "title": "t",
            "message": "body",
            "sound": "brrr",
            "thread_id": "grp",
        }

    def test_bearer_header_from_arg():
        m, _ = _capture()
        with mock.patch("requests.request", m):
            send("hi", token="secret-token")
        assert m.call_args.kwargs["headers"]["Authorization"] == "Bearer secret-token"

    def test_bearer_header_from_env():
        m, _ = _capture()
        with (
            mock.patch.dict(os.environ, {TOKEN_ENV_VAR: "env-token"}),
            mock.patch("requests.request", m),
        ):
            send("hi")
        assert m.call_args.kwargs["headers"]["Authorization"] == "Bearer env-token"

    def test_missing_token_raises():
        with mock.patch.dict(os.environ, {}, clear=True), pytest.raises(HisssAuthError):
            send("hi")

    def test_requires_title_or_message():
        with pytest.raises(HisssError):
            send(token="t")

    def test_volume_out_of_range_raises():
        with pytest.raises(HisssError):
            send("hi", volume=1.5, token="t")

    def test_unknown_sound_raises():
        with pytest.raises(HisssError):
            send("hi", sound="kazoo", token="t")

    def test_unknown_interruption_level_raises():
        with pytest.raises(HisssError):
            send("hi", interruption_level="loud", token="t")

    def test_datetime_serialized_to_iso_z():
        m, _ = _capture()
        when = datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=UTC)
        with mock.patch("requests.request", m):
            send("hi", expiration_date=when, token="t")
        assert m.call_args.kwargs["json"]["expiration_date"] == "2026-01-02T03:04:05.678Z"

    def test_string_expiration_passed_through():
        m, _ = _capture()
        with mock.patch("requests.request", m):
            send("hi", expiration_date="2026-01-01T00:00:00.000Z", token="t")
        assert m.call_args.kwargs["json"]["expiration_date"] == "2026-01-01T00:00:00.000Z"

    def test_non_2xx_raises_without_token_in_message():
        fake = _FakeResponse(status_code=401, text="unauthorized")
        with (
            mock.patch("requests.request", mock.Mock(return_value=fake)),
            pytest.raises(HisssAPIError) as info,
        ):
            send("hi", token="super-secret")
        assert info.value.status == 401
        assert "super-secret" not in str(info.value)

    def test_empty_body_returns_empty_dict():
        fake = _FakeResponse(status_code=200, content=b"")
        with mock.patch("requests.request", mock.Mock(return_value=fake)):
            assert send("hi", token="t") == {}


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
