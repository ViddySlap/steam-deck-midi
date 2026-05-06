"""Tiny stdlib-based client for Resolume's local REST API.

Avoids an external `requests` dependency. The web server lives at
`http://127.0.0.1:8080` by default and exposes the parameter tree used by the
OSC API.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 1.5


class ResolumeRestError(RuntimeError):
    """Raised when a REST call to Resolume fails."""


class ResolumeRestClient:
    """Minimal Resolume Arena REST client (stdlib only)."""

    def __init__(self, base_url: str = "http://127.0.0.1:8080", timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self._base}{path}"

    def get(self, path: str) -> Any:
        url = self._url(path)
        try:
            with urllib.request.urlopen(url, timeout=self._timeout) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as exc:
            raise ResolumeRestError(f"GET {url} failed: {exc}") from exc

    def put(self, path: str, body: dict) -> None:
        url = self._url(path)
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                _ = response.read()
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            raise ResolumeRestError(f"PUT {url} failed: {exc}") from exc

    def get_layer(self, layer_index: int) -> dict:
        return self.get(f"/api/v1/composition/layers/{layer_index}")

    def get_group(self, group_index: int) -> dict:
        return self.get(f"/api/v1/composition/groups/{group_index}")

    def set_layer_bypassed(self, layer_index: int, bypassed: bool) -> None:
        self.put(
            f"/api/v1/composition/layers/{layer_index}",
            {"bypassed": {"value": bool(bypassed)}},
        )

    def set_group_bypassed(self, group_index: int, bypassed: bool) -> None:
        self.put(
            f"/api/v1/composition/groups/{group_index}",
            {"bypassed": {"value": bool(bypassed)}},
        )
