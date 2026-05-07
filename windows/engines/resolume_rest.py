"""Minimal Resolume Arena REST client for the OSC sync engine.

Scope is intentionally narrow:
- GET /api/v1/composition - walk once on demand to build a path -> param map.
- GET /api/v1/parameter/by-id/{id} - read a single parameter's current value.
- PUT /api/v1/parameter/by-id/{id} - write a parameter value.

Uses urllib only - no external dependencies. Calls are blocking; the OSC sync
engine wraps the actual sync pass in a worker thread so the receive loop
stays responsive.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

LOGGER = logging.getLogger(__name__)


class ResolumeRestError(Exception):
    """Raised on REST failures the caller should know about."""


class ResolumeRestClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8080", timeout_seconds: float = 1.5) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def get_composition(self) -> dict[str, Any]:
        return self._get("/api/v1/composition")

    def get_parameter(self, param_id: int) -> dict[str, Any]:
        return self._get(f"/api/v1/parameter/by-id/{param_id}")

    def put_parameter(self, param_id: int, value: Any) -> None:
        self._put(f"/api/v1/parameter/by-id/{param_id}", {"value": value})

    def _get(self, path: str) -> dict[str, Any]:
        url = self._base_url + path
        try:
            with urllib.request.urlopen(url, timeout=self._timeout) as resp:
                payload = resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ResolumeRestError(f"GET {url} failed: {exc}") from exc
        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResolumeRestError(f"GET {url} returned invalid JSON: {exc}") from exc

    def _put(self, path: str, body: dict[str, Any]) -> None:
        url = self._base_url + path
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="PUT", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ResolumeRestError(f"PUT {url} failed: {exc}") from exc
