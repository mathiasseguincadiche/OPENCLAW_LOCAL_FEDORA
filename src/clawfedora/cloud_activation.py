"""Activation of the cloud: it switches on only if privacy AND budget work together.

``enable`` runs self-tests with no network and no real key. The decisive one starts the REAL
gateway with the REAL filter and the REAL ledger in front of a fake provider, and checks that a
secret is stopped before anything is reserved or sent, that a clean call is forwarded with the
provider key only and counted with its cost, and that a call beyond the cap is refused before
it leaves. Only if every check passes is the activation record written.
"""

from __future__ import annotations

import http.client
import json
import os
import random
import re
import string
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from clawfedora.cloud_budget import BudgetRefused, Ledger
from clawfedora.cloud_gateway import Refused, make_server, read_upstream_key
from clawfedora.cloud_privacy import PrivacyFilter
from clawfedora.cloud_state import (
    CLOUD_STATE,
    cloud_status,
    revoke_activation,
    write_activation,
)
from clawfedora.core_config import core_contract
from clawfedora.core_contracts import validate_core_contracts
from clawfedora.project_common import assert_no_symlinks

KEY_PATTERN = re.compile(r"sk-or-[A-Za-z0-9_\-]{12,}")
SELFTEST_KEY = "sk-or-selftest-" + "x" * 24


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# -- provider key -------------------------------------------------------------------
def key_path(repo_root: Path, runtime: Path) -> Path:
    policy = core_contract(repo_root, "cloud_policy.yaml")
    return runtime / "state" / str(policy["gateway"]["upstream_key_file"])


def set_key(repo_root: Path, runtime: Path, key: str, *, replace: bool = False) -> Path:
    """Store the provider key, private (0600), in the one file only the gateway reads."""
    key = key.strip()
    if not KEY_PATTERN.fullmatch(key):
        raise ValueError("clé du fournisseur invalide: une clé OpenRouter commence par sk-or-")
    path = key_path(repo_root, runtime)
    if not (runtime / "state").is_dir():
        raise ValueError("runtime géré requis avant de stocker une clé")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    if path.is_symlink():
        raise ValueError("fichier de clé lié interdit")
    if path.exists() and not replace:
        raise ValueError("une clé existe déjà: --replace pour la remplacer")
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(key + "\n")
    temporary.replace(path)
    path.chmod(0o600)
    return path


def fingerprint(key: str) -> str:
    return f"{key[:9]}…{key[-4:]}"


# -- self-tests ---------------------------------------------------------------------
def _secret() -> str:
    """A synthetic token, built here so no credential-like string sits in the repository."""
    return "gh" + "p_" + "".join(random.Random(3).choices(string.ascii_letters, k=36))


def check_policy(repo_root: Path) -> Check:
    failures, _ = validate_core_contracts(repo_root)
    if failures:
        return Check("contrats", False, "; ".join(failures[:3]))
    return Check("contrats", True, "tous les contrats du dépôt sont valides")


def check_key(repo_root: Path, runtime: Path) -> Check:
    policy = core_contract(repo_root, "cloud_policy.yaml")
    try:
        key = read_upstream_key(runtime, str(policy["gateway"]["upstream_key_file"]))
    except Refused as exc:
        return Check("clé du fournisseur", False, exc.message)
    if not KEY_PATTERN.fullmatch(key):
        return Check("clé du fournisseur", False, "format inattendu (sk-or-… attendu)")
    return Check("clé du fournisseur", True, f"présente, privée (0600) : {fingerprint(key)}")


def check_declaration(
    repo_root: Path, key_limit_usd: float | None, prepaid: bool
) -> Check:
    budget = core_contract(repo_root, "cloud_policy.yaml")["budget"]
    maximum = float(budget["monthly_cap_eur"]) / float(budget["eur_per_usd"])
    if not prepaid:
        return Check(
            "plafond chez le fournisseur", False,
            "confirmer des crédits prépayés sans rechargement automatique (--confirm-prepaid)",
        )
    if key_limit_usd is None or not 0 < key_limit_usd <= maximum:
        return Check(
            "plafond chez le fournisseur", False,
            f"déclarer la limite posée sur la clé (--value en $), au plus {maximum:.2f} $ "
            f"(= {budget['monthly_cap_eur']} € / {budget['eur_per_usd']})",
        )
    return Check(
        "plafond chez le fournisseur", True,
        f"crédits prépayés confirmés, limite de clé déclarée : {key_limit_usd:g} $",
    )


def check_filter() -> Check:
    """The filter stops a secret wherever it travels and lets a course example through."""
    privacy = PrivacyFilter()
    secret = _secret()
    for role in ("user", "assistant", "system", "tool"):
        found = privacy.scan_request({"messages": [{"role": role, "content": "x " + secret}]})
        if not found:
            return Check("filtre de confidentialité", False, f"secret non bloqué ({role})")
    example = 'subscription_id = "00000000-0000-0000-0000-000000000000"\npassword = var.pwd'
    if privacy.scan_request({"messages": [{"role": "user", "content": example}]}):
        return Check("filtre de confidentialité", False, "un exemple de cours est bloqué")
    return Check("filtre de confidentialité", True, "secret bloqué partout, exemples de cours libres")


def _small_cap_policy(repo_root: Path, cap_eur: float) -> dict[str, Any]:
    policy = core_contract(repo_root, "cloud_policy.yaml")
    policy["budget"] = {**policy["budget"], "monthly_cap_eur": cap_eur}
    return policy


def check_budget(repo_root: Path) -> Check:
    """Reserve, settle, refuse at the cap: on a throwaway ledger with a tiny cap."""
    with tempfile.TemporaryDirectory(prefix="clawfedora-budget-") as temporary:
        runtime = Path(temporary)
        (runtime / "state").mkdir()
        ledger = Ledger(runtime, _small_cap_policy(repo_root, 1.0))
        try:
            ledger.reserve(input_tokens=100, max_output_tokens=100).settle(
                {"cost": 0.0001, "prompt_tokens": 100, "completion_tokens": 10}, "ok"
            )
            ledger.reserve(input_tokens=100, max_output_tokens=100).settle(None, "failed")
            summary = ledger.summary()
            if (summary.calls_ok, summary.calls_failed) != (1, 1) or not (
                0 < summary.spent_usd < 0.001
            ):
                return Check("budget", False, f"comptage inattendu: {summary}")
        except BudgetRefused as exc:
            return Check("budget", False, f"refus inattendu: {exc}")
        try:
            ledger.reserve(input_tokens=10_000_000, max_output_tokens=0)
        except BudgetRefused:
            return Check("budget", True, "réservation, règlement et refus au plafond vérifiés")
        return Check("budget", False, "un appel au-delà du plafond n'a pas été refusé")


class _Provider(BaseHTTPRequestHandler):
    calls: list[dict[str, Any]]

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.calls.append({"authorization": self.headers.get("Authorization"), "body": body})
        raw = json.dumps(
            {
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5, "cost": 0.0001},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def check_together(repo_root: Path) -> Check:
    """The real gateway, filter and ledger, against a fake provider, in one scenario."""
    policy = core_contract(repo_root, "cloud_policy.yaml")
    model = str(policy["model"]["upstream_id"])
    calls: list[dict[str, Any]] = []
    handler = type("Provider", (_Provider,), {"calls": calls})
    provider = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=provider.serve_forever, kwargs={"poll_interval": 0.02},
                     daemon=True).start()
    gateway = None
    try:
        with tempfile.TemporaryDirectory(prefix="clawfedora-activation-") as temporary:
            runtime = Path(temporary)
            (runtime / "state").mkdir()
            ledger = Ledger(runtime, _small_cap_policy(repo_root, 0.1))
            gateway = make_server(
                repo_root, runtime, budget=ledger, activation_check=lambda: None, port=0,
                upstream_base_url=f"http://127.0.0.1:{provider.server_port}/v1",
                key_reader=lambda: SELFTEST_KEY,
            )
            threading.Thread(target=gateway.serve_forever, kwargs={"poll_interval": 0.02},
                             daemon=True).start()

            def post(content: str, token: str | None = None, role: str = "user") -> int:
                messages = [{"role": "user", "content": "bonjour"}]
                if role != "user" or content != "bonjour":
                    messages.append({"role": role, "content": content})
                body = {"model": model, "messages": messages}
                connection = http.client.HTTPConnection("127.0.0.1", gateway.server_port, timeout=10)
                connection.request(
                    "POST", policy["gateway"]["path_prefix"] + "/chat/completions",
                    body=json.dumps(body),
                    headers={"Content-Type": "application/json",
                             "Authorization": "Bearer " + (token or gateway.token)},
                )
                status = connection.getresponse().status
                connection.close()
                return status

            if post("bonjour", token="wrong") != 401:
                return Check("filtre et budget ensemble", False, "un jeton faux n'est pas refusé")
            if post("résultat: " + _secret(), role="tool") != 451:
                return Check("filtre et budget ensemble", False, "un secret n'est pas bloqué")
            if calls or ledger.summary().calls_ok + ledger.summary().pending:
                return Check("filtre et budget ensemble", False,
                             "un secret a déclenché une réservation ou un envoi")
            if post("bonjour") != 200 or len(calls) != 1:
                return Check("filtre et budget ensemble", False, "un appel sain n'est pas relayé")
            if calls[0]["authorization"] != "Bearer " + SELFTEST_KEY or (
                gateway.token in json.dumps(calls[0])
            ):
                return Check("filtre et budget ensemble", False,
                             "le fournisseur doit recevoir la clé, jamais le jeton local")
            if ledger.summary().calls_ok != 1:
                return Check("filtre et budget ensemble", False, "l'appel n'est pas compté")
            ledger.record_invoice(0.0999)
            if post("bonjour") != 402 or len(calls) != 1:
                return Check("filtre et budget ensemble", False,
                             "un appel au-delà du plafond n'est pas refusé avant l'envoi")
    finally:
        if gateway is not None:
            gateway.shutdown()
            gateway.server_close()
        provider.shutdown()
        provider.server_close()
    return Check(
        "filtre et budget ensemble", True,
        "secret bloqué avant réservation et envoi, appel sain compté, plafond refusé avant l'envoi",
    )


def fetch_key_info(base_url: str, key: str, timeout: float = 15.0) -> dict[str, Any]:
    """Ask the provider about the key (its limit). The only network call of this module."""
    request = urllib.request.Request(
        base_url.rstrip("/") + "/key", headers={"Authorization": "Bearer " + key}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        value = json.loads(response.read())
    data = value.get("data") if isinstance(value, dict) else None
    if not isinstance(data, dict):
        raise ValueError("réponse inattendue du fournisseur")
    return data


def check_online(
    repo_root: Path, runtime: Path, key_limit_usd: float | None,
    fetch: Callable[..., dict[str, Any]] = fetch_key_info,
) -> Check:
    policy = core_contract(repo_root, "cloud_policy.yaml")
    try:
        key = read_upstream_key(runtime, str(policy["gateway"]["upstream_key_file"]))
        info = fetch(str(policy["upstream"]["base_url"]), key)
    except (Refused, OSError, ValueError) as exc:
        return Check("limite de clé (en ligne)", False, f"vérification impossible: {exc}")
    limit = info.get("limit")
    if not isinstance(limit, int | float) or isinstance(limit, bool) or limit <= 0:
        return Check("limite de clé (en ligne)", False,
                     "aucune limite de crédit sur la clé: en poser une chez le fournisseur")
    if key_limit_usd is not None and limit > key_limit_usd + 1e-9:
        return Check("limite de clé (en ligne)", False,
                     f"la limite réelle ({limit:g} $) dépasse celle déclarée ({key_limit_usd:g} $)")
    return Check("limite de clé (en ligne)", True, f"limite réelle de la clé : {limit:g} $")


def run_selftests(
    repo_root: Path,
    runtime: Path,
    *,
    key_limit_usd: float | None,
    prepaid: bool,
    verify_online: bool = False,
    fetch: Callable[..., dict[str, Any]] = fetch_key_info,
) -> list[Check]:
    checks = [
        check_policy(repo_root),
        check_key(repo_root, runtime),
        check_declaration(repo_root, key_limit_usd, prepaid),
        check_filter(),
        check_budget(repo_root),
        check_together(repo_root),
    ]
    if verify_online:
        checks.append(check_online(repo_root, runtime, key_limit_usd, fetch))
    return checks


def enable(
    repo_root: Path,
    runtime: Path,
    *,
    key_limit_usd: float | None,
    prepaid: bool,
    verify_online: bool = False,
    apply: bool = False,
    fetch: Callable[..., dict[str, Any]] = fetch_key_info,
) -> tuple[list[Check], bool]:
    """Run every self-test. The activation is written only with ``apply`` and no failure."""
    checks = run_selftests(
        repo_root, runtime, key_limit_usd=key_limit_usd, prepaid=prepaid,
        verify_online=verify_online, fetch=fetch,
    )
    if not all(check.ok for check in checks):
        return checks, False
    if not apply:
        return checks, False
    now = _stamp()
    write_activation(
        runtime,
        {"privacy_filter": now, "budget_guard": now},
        {"key_limit_usd": key_limit_usd, "prepaid_credits": True,
         "verified_online": verify_online},
    )
    return checks, True


def disable(runtime: Path) -> None:
    revoke_activation(runtime)


# -- service ------------------------------------------------------------------------
def render_unit(repo_root: Path, runtime: Path, unit_root: Path) -> Path:
    """The systemd user unit of the gateway, written like the other managed units."""
    for path in (repo_root, runtime, unit_root):
        if not path.is_absolute() or not re.fullmatch(r"[A-Za-z0-9_./-]+", str(path)):
            raise ValueError("chemins absolus sans espace ni caractère systemd spécial requis")
        for parent in (path, *path.parents):
            if parent.is_symlink():
                raise ValueError("chemin lié interdit")
    if not (runtime / ".openclaw-fedora-runtime").is_file():
        raise ValueError("runtime géré requis")
    state = runtime / CLOUD_STATE
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    assert_no_symlinks(state, label="état cloud")
    python = runtime / "runtime/venv/bin/python"
    unit_root.mkdir(parents=True, exist_ok=True)
    unit = unit_root / "clawfedora-cloud-gateway.service"
    if unit.is_symlink():
        raise ValueError("unité liée interdite")
    header = "# Managed by OPENCLAW_LOCAL_FEDORA\n"
    if unit.exists() and not unit.read_text().startswith(header):
        raise ValueError("unité existante non gérée: clawfedora-cloud-gateway")
    unit.write_text(
        header
        + "[Unit]\nDescription=Atelier IA - passerelle cloud locale (filtre et budget)\n"
        + "\n[Service]\nUMask=0077\nRestart=on-failure\nRestartSec=5\n"
        + f"Environment=OPENCLAW_LOCAL_FEDORA_ROOT={runtime}\n"
        + f"ExecStart={python} -m clawfedora.cloud_gateway "
        + f"--root {repo_root} --runtime-root {runtime}\n"
        + "NoNewPrivileges=true\n\n[Install]\nWantedBy=default.target\n"
    )
    return unit


__all__ = [
    "Check", "check_budget", "check_declaration", "check_filter", "check_key", "check_online",
    "check_policy", "check_together", "cloud_status", "disable", "enable", "fetch_key_info",
    "fingerprint", "key_path", "render_unit", "run_selftests", "set_key",
]
