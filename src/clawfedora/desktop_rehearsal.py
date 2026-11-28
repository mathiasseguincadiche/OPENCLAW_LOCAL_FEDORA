"""Consent and verification rehearsal for a synthetic Wayland window."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from uuid import uuid4

from clawfedora import desktop_portal

WINDOW = "atlas-window"
MODES = ("observe", "pointer")
DETAILS = "details-button"
TTL_SECONDS = 300
MAX_OBSERVATIONS = 8


@dataclass(frozen=True)
class Observation:
    session: str
    window: str
    revision: int
    details_open: bool


class DesktopRehearsal:
    """A deterministic session over built-in data, with no compositor adapter."""

    def __init__(
        self, mode: str, *, clock: Callable[[], float] = time.monotonic,
        capabilities: Mapping[str, object] | None = None,
    ) -> None:
        if mode not in MODES:
            raise ValueError("mode de recette inconnu")
        if capabilities is not None:
            _require_capabilities(mode, capabilities)
        self.mode = mode
        self.session = uuid4().hex
        self._clock = clock
        self._expires_at: float | None = None
        self.closed = False
        self._revision = 0
        self._details_open = False
        self._observations = 0
        self._last: Observation | None = None
        self.events: list[str] = []

    def consent(self, *, window: str, mode: str, accepted: bool) -> None:
        if self.closed or self._expires_at is not None:
            raise ValueError("session déjà décidée")
        if accepted is not True or window != WINDOW or mode != self.mode:
            self._close("CONSENT_REFUSED")
            raise ValueError("consentement requis pour la fenêtre et le mode exacts")
        self._expires_at = self._clock() + TTL_SECONDS
        self.events.append("CONSENT_GRANTED")

    def _close(self, event: str) -> None:
        if not self.closed:
            self.closed = True
            self._last = None
            self.events.append(event)

    def revoke(self) -> None:
        self._close("REVOKED")

    def portal_closed(self) -> None:
        self._close("PORTAL_CLOSED")

    def _require_window(self, window: str) -> None:
        if self.closed:
            raise ValueError("session fermée")
        if self._expires_at is None:
            raise ValueError("consentement en attente")
        if self._clock() >= self._expires_at:
            self._close("EXPIRED")
            raise ValueError("consentement expiré")
        if window != WINDOW:
            self._close("WINDOW_CHANGED")
            raise ValueError("identité de fenêtre divergente")

    def observe(self, *, window: str) -> Observation:
        self._require_window(window)
        if self._observations >= MAX_OBSERVATIONS:
            self._close("OBSERVATION_LIMIT")
            raise ValueError("limite d'observations atteinte")
        self._observations += 1
        self._last = Observation(self.session, window, self._revision, self._details_open)
        self.events.append("OBSERVED")
        return self._last

    def open_details(
        self, observation: Observation, *, window: str, target: str, approved: bool,
    ) -> None:
        self._require_window(window)
        if self.mode != "pointer" or approved is not True or target != DETAILS:
            raise ValueError("ouverture des détails non approuvée")
        if self._last != observation or observation.details_open:
            raise ValueError("observation absente, divergente ou périmée")
        self._details_open = True
        self._revision += 1
        self._last = None
        self.events.append("DETAILS_OPENED")


def _require_capabilities(mode: str, capabilities: Mapping[str, object]) -> None:
    required = ["window_advertised"]
    if mode == "pointer":
        required += ["pointer_advertised", "eis_api_in_version"]
    missing = [key for key in required if capabilities.get(key) is not True]
    if capabilities.get("status") not in ("PROBED", "INCOMPLETE") or missing:
        raise ValueError("capacités du portail à confirmer : " + ", ".join(missing or required))


def simulate(
    mode: str, *, capabilities: Mapping[str, object] | None = None,
) -> dict[str, object]:
    exercise = DesktopRehearsal(mode, capabilities=capabilities)
    exercise.consent(window=WINDOW, mode=mode, accepted=True)
    initial = exercise.observe(window=WINDOW)
    final = initial
    if mode == "pointer":
        exercise.open_details(initial, window=WINDOW, target=DETAILS, approved=True)
        final = exercise.observe(window=WINDOW)
    exercise.revoke()
    return {
        "scope": "SYNTHETIC_NO_COMPOSITOR",
        "mode": mode,
        "before": asdict(initial),
        "after": asdict(final),
        "events": exercise.events,
        "closed": exercise.closed,
    }


def add_desktop_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    command = subparsers.add_parser("desktop-rehearsal", help="simuler le consentement Wayland")
    command.add_argument("--mode", choices=MODES, default="observe")
    command.add_argument("--require-portal", action="store_true",
                         help="contrôler les capacités annoncées avant la simulation")


def run_desktop_command(args: argparse.Namespace) -> int:
    capabilities = (
        desktop_portal.probe(desktop_portal.session_type()) if args.require_portal else None
    )
    try:
        result = simulate(args.mode, capabilities=capabilities)
    except ValueError as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
