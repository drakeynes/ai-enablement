"""Minimal Slack Web API client for ingestion.

Hand-rolled against httpx (already a transitive dep via supabase-py)
rather than pulling in slack-sdk — we use four API methods in V1 and
slack-sdk would be ~30% of our dep footprint for marginal convenience.

Handles:
  - Bearer-token auth from `SLACK_BOT_TOKEN`.
  - Cursor pagination via `response_metadata.next_cursor`.
  - Rate-limit backoff honoring Slack's `Retry-After` header on 429s.
  - `ok: false` response error propagation with the Slack-reported
    error string (e.g. `not_in_channel`, `channel_not_found`).

Methods exposed (thin wrappers):
  - `auth_test()` — bot identity.
  - `conversations_list(...)` — find channels by name.
  - `conversations_info(channel)` — channel metadata.
  - `conversations_members(channel)` — membership list.
  - `conversations_history(channel, oldest, latest)` — messages
    (auto-paginated).
  - `conversations_replies(channel, thread_ts)` — thread replies
    (auto-paginated).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Iterator

import httpx

from shared.logging import logger

_BASE_URL = "https://slack.com/api"
_DEFAULT_TIMEOUT_SECONDS = 30
_DEFAULT_MAX_RETRIES = 5
_DEFAULT_PAGE_LIMIT = 200


class SlackAPIError(RuntimeError):
    """Raised when Slack returns `ok: false` with an error code."""

    def __init__(self, method: str, error: str, response_json: dict[str, Any]):
        super().__init__(f"Slack API {method} failed: {error}")
        self.method = method
        self.error = error
        self.response = response_json


class SlackNotInChannel(SlackAPIError):
    """Bot is not a member of the requested channel. Surfaced as its own
    type so the pipeline can report per-channel membership status
    cleanly rather than treat it as a generic error."""


@dataclass(frozen=True)
class ApiCallStats:
    """Aggregate HTTP call counter for cost / volume reporting."""

    calls_made: int = 0
    retries: int = 0
    rate_limit_hits: int = 0


class SlackClient:
    """Stateful Slack Web API client with counters."""

    def __init__(
        self,
        token: str | None = None,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._token = token or os.getenv("SLACK_BOT_TOKEN")
        if not self._token:
            raise RuntimeError(
                "SLACK_BOT_TOKEN is not set. Copy .env.example to .env.local "
                "and fill in the bot token."
            )
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._http = http_client or httpx.Client(
            base_url=_BASE_URL,
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {self._token}"},
        )
        self.calls_made = 0
        self.retries = 0
        self.rate_limit_hits = 0

    # -----------------------------------------------------------------------
    # Typed method wrappers
    # -----------------------------------------------------------------------

    def auth_test(self) -> dict[str, Any]:
        return self._call("auth.test", method="POST")

    def conversations_list(
        self,
        *,
        types: str = "public_channel,private_channel",
        limit: int = _DEFAULT_PAGE_LIMIT,
    ) -> Iterator[dict[str, Any]]:
        """Yield every channel page-by-page until Slack's cursor is exhausted."""
        yield from self._paginate(
            "conversations.list",
            {"types": types, "limit": limit},
            key="channels",
        )

    def conversations_info(self, channel: str) -> dict[str, Any]:
        return self._call("conversations.info", params={"channel": channel})

    def conversations_members(self, channel: str) -> list[str]:
        members: list[str] = []
        for page in self._paginate(
            "conversations.members",
            {"channel": channel, "limit": _DEFAULT_PAGE_LIMIT},
            key="members",
        ):
            members.append(page)
        return members

    def conversations_history(
        self,
        channel: str,
        *,
        oldest: str | None = None,
        latest: str | None = None,
        limit: int = _DEFAULT_PAGE_LIMIT,
    ) -> Iterator[dict[str, Any]]:
        params: dict[str, Any] = {"channel": channel, "limit": limit}
        if oldest is not None:
            params["oldest"] = oldest
        if latest is not None:
            params["latest"] = latest
        yield from self._paginate(
            "conversations.history", params, key="messages",
            not_in_channel_raises=SlackNotInChannel,
        )

    def conversations_replies(
        self,
        channel: str,
        thread_ts: str,
        *,
        limit: int = _DEFAULT_PAGE_LIMIT,
    ) -> Iterator[dict[str, Any]]:
        yield from self._paginate(
            "conversations.replies",
            {"channel": channel, "ts": thread_ts, "limit": limit},
            key="messages",
            not_in_channel_raises=SlackNotInChannel,
        )

    def users_info(self, user: str) -> dict[str, Any]:
        return self._call("users.info", params={"user": user})

    # -----------------------------------------------------------------------
    # Transport
    # -----------------------------------------------------------------------

    def _call(
        self,
        endpoint: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute one Slack API call with retry on 429 + transient 5xx."""
        for attempt in range(self._max_retries + 1):
            try:
                if method == "GET":
                    resp = self._http.get("/" + endpoint, params=params)
                else:
                    resp = self._http.post("/" + endpoint, data=params)
            except httpx.RequestError as exc:
                if attempt >= self._max_retries:
                    raise
                self.retries += 1
                logger.warning(
                    "Slack %s transport error (attempt %d): %s", endpoint, attempt + 1, exc
                )
                time.sleep(min(2**attempt, 30))
                continue
            self.calls_made += 1

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "1"))
                self.rate_limit_hits += 1
                self.retries += 1
                logger.warning(
                    "Slack %s rate-limited; sleeping %.1fs", endpoint, retry_after
                )
                time.sleep(retry_after + 0.5)
                continue

            if resp.status_code >= 500:
                if attempt >= self._max_retries:
                    resp.raise_for_status()
                self.retries += 1
                logger.warning(
                    "Slack %s %d (attempt %d); backing off",
                    endpoint, resp.status_code, attempt + 1,
                )
                time.sleep(min(2**attempt, 30))
                continue

            resp.raise_for_status()
            payload = resp.json()
            if not payload.get("ok", False):
                error = payload.get("error", "unknown_error")
                if error == "not_in_channel":
                    raise SlackNotInChannel(endpoint, error, payload)
                raise SlackAPIError(endpoint, error, payload)
            return payload

        raise SlackAPIError(endpoint, "max_retries_exceeded", {})

    def _paginate(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        key: str,
        not_in_channel_raises: type[SlackAPIError] | None = None,
    ) -> Iterator[Any]:
        cursor: str | None = None
        while True:
            call_params = dict(params)
            if cursor:
                call_params["cursor"] = cursor
            try:
                payload = self._call(endpoint, params=call_params)
            except SlackNotInChannel:
                if not_in_channel_raises is not None:
                    raise
                raise
            for item in payload.get(key, []) or []:
                yield item
            cursor = (payload.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break

    def stats(self) -> ApiCallStats:
        return ApiCallStats(
            calls_made=self.calls_made,
            retries=self.retries,
            rate_limit_hits=self.rate_limit_hits,
        )

    def close(self) -> None:
        self._http.close()


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


def find_channel_by_name(
    client: SlackClient, name: str
) -> dict[str, Any] | None:
    """Scan conversations.list for a channel whose `name` matches.

    Slack channel names are unique per workspace, case-sensitive, no
    leading `#`. Accepts inputs with or without the leading `#`.
    """
    name_clean = name.lstrip("#")
    for channel in client.conversations_list():
        if channel.get("name") == name_clean:
            return channel
    return None
