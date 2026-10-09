"""The cloud switches on only when privacy and budget work together, and says why not."""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

import pytest

from clawfedora import cloud_activation as activation
from clawfedora import cloud_cli
from clawfedora.cloud_privacy import Finding
from clawfedora.cloud_state import cloud_status, read_activation, write_activation

ROOT = Path(__file__).resolve().parents[1]
KEY = "sk-or-v1-" + "ab12" * 8


@pytest.fixture
def runtime(tmp_path: Path) -> Path:
    (tmp_path / "state").mkdir()
    (tmp_path / ".openclaw-fedora-runtime").write_text("managed\n")
    return tmp_path


def enable(runtime: Path, **options: Any) -> tuple[list[activation.Check], bool]:
    options.setdefault("key_limit_usd", 12.0)
    options.setdefault("prepaid", True)
    return activation.enable(ROOT, runtime, **options)


def failed(checks: list[activation.Check]) -> list[str]:
    return [check.name for check in checks if not check.ok]


# -- key ----------------------------------------------------------------------------
def test_the_key_is_stored_private_and_only_in_its_file(runtime: Path) -> None:
    path = activation.set_key(ROOT, runtime, "  " + KEY + "\n")
    assert path.read_text().strip() == KEY
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert not list(path.parent.glob("*.tmp"))
    assert KEY not in "".join(
        p.read_text() for p in runtime.rglob("*") if p.is_file() and p != path
    )


@pytest.mark.parametrize("bad", ["", "ghp_nothing", "sk-or-", "sk-or-court", "sk-or-v1-a b c d e f"])
def test_a_malformed_key_is_refused(runtime: Path, bad: str) -> None:
    with pytest.raises(ValueError, match="clé"):
        activation.set_key(ROOT, runtime, bad)


def test_replacing_a_key_is_explicit_and_symlinks_are_refused(runtime: Path) -> None:
    activation.set_key(ROOT, runtime, KEY)
    with pytest.raises(ValueError, match="--replace"):
        activation.set_key(ROOT, runtime, KEY.replace("ab12", "cd34"))
    activation.set_key(ROOT, runtime, KEY.replace("ab12", "cd34"), replace=True)
    path = activation.key_path(ROOT, runtime)
    path.unlink()
    path.symlink_to(runtime / "elsewhere")
    with pytest.raises(ValueError, match="lié"):
        activation.set_key(ROOT, runtime, KEY, replace=True)


def test_the_key_needs_a_managed_runtime(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="runtime"):
        activation.set_key(ROOT, tmp_path, KEY)


def test_the_fingerprint_never_shows_the_whole_key() -> None:
    shown = activation.fingerprint(KEY)
    assert shown.startswith("sk-or-v1-") and shown.endswith(KEY[-4:]) and KEY not in shown


# -- activation ---------------------------------------------------------------------
def test_everything_passing_without_apply_changes_nothing(runtime: Path) -> None:
    activation.set_key(ROOT, runtime, KEY)
    checks, activated = enable(runtime)
    assert not failed(checks) and activated is False
    assert not cloud_status(runtime, ROOT)[0]


def test_apply_writes_the_activation_with_both_proofs_and_the_declaration(runtime: Path) -> None:
    activation.set_key(ROOT, runtime, KEY)
    checks, activated = enable(runtime, apply=True)
    assert not failed(checks) and activated
    assert cloud_status(runtime, ROOT)[0]
    record = read_activation(runtime)
    assert set(record["verified"]) == {"privacy_filter", "budget_guard"}
    assert record["declared"] == {
        "key_limit_usd": 12.0, "prepaid_credits": True, "verified_online": False}
    assert KEY not in str(record)


def test_without_a_key_nothing_is_activated(runtime: Path) -> None:
    checks, activated = enable(runtime, apply=True)
    assert failed(checks) == ["clé du fournisseur"] and not activated
    assert not cloud_status(runtime, ROOT)[0]


def test_a_key_with_open_permissions_is_refused(runtime: Path) -> None:
    path = activation.set_key(ROOT, runtime, KEY)
    path.chmod(0o644)
    checks, activated = enable(runtime, apply=True)
    assert "clé du fournisseur" in failed(checks) and not activated


@pytest.mark.parametrize("limit", [None, 0.0, -5.0, 19.24, 25.0, 100.0])
def test_a_key_limit_above_the_cap_converted_to_dollars_is_refused(
    runtime: Path, limit: float | None
) -> None:
    activation.set_key(ROOT, runtime, KEY)
    checks, activated = enable(runtime, key_limit_usd=limit, apply=True)
    assert failed(checks) == ["plafond chez le fournisseur"] and not activated


def test_the_highest_acceptable_key_limit_is_the_cap_over_the_factor(runtime: Path) -> None:
    activation.set_key(ROOT, runtime, KEY)
    checks, _ = enable(runtime, key_limit_usd=19.2)
    assert not failed(checks)


def test_prepaid_credits_must_be_confirmed(runtime: Path) -> None:
    activation.set_key(ROOT, runtime, KEY)
    checks, activated = enable(runtime, prepaid=False, apply=True)
    assert failed(checks) == ["plafond chez le fournisseur"] and not activated
    assert "prépayés" in checks[2].detail


def test_a_filter_that_lets_a_secret_through_blocks_the_activation(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Blind(activation.PrivacyFilter):
        def scan_request(self, body: dict[str, Any]) -> list[Finding]:
            return []

    activation.set_key(ROOT, runtime, KEY)
    monkeypatch.setattr(activation, "PrivacyFilter", Blind)
    monkeypatch.setattr("clawfedora.cloud_gateway.PrivacyFilter", Blind)
    checks, activated = enable(runtime, apply=True)
    assert "filtre de confidentialité" in failed(checks)
    assert "filtre et budget ensemble" in failed(checks) and not activated
    assert not cloud_status(runtime, ROOT)[0]


def test_a_filter_that_blocks_course_examples_blocks_the_activation(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Paranoid(activation.PrivacyFilter):
        def scan_request(self, body: dict[str, Any]) -> list[Finding]:
            return [Finding("token", "messages[0].user")]

    monkeypatch.setattr(activation, "PrivacyFilter", Paranoid)
    activation.set_key(ROOT, runtime, KEY)
    checks, activated = enable(runtime, apply=True)
    assert "filtre de confidentialité" in failed(checks) and not activated


def test_a_budget_that_never_refuses_blocks_the_activation(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Unlimited(activation.Ledger):
        def reserve(self, *, input_tokens: int, max_output_tokens: int) -> Any:
            class Free:
                def settle(self, usage: Any, status: str) -> None:
                    pass

            return Free()

    monkeypatch.setattr(activation, "Ledger", Unlimited)
    activation.set_key(ROOT, runtime, KEY)
    checks, activated = enable(runtime, apply=True)
    assert "budget" in failed(checks) and "filtre et budget ensemble" in failed(checks)
    assert not activated and not cloud_status(runtime, ROOT)[0]


def test_the_self_tests_leave_no_trace_in_the_real_runtime(runtime: Path) -> None:
    activation.set_key(ROOT, runtime, KEY)
    before = {p.relative_to(runtime) for p in runtime.rglob("*")}
    enable(runtime)
    assert {p.relative_to(runtime) for p in runtime.rglob("*")} == before


def test_disable_is_the_single_rollback(runtime: Path) -> None:
    activation.set_key(ROOT, runtime, KEY)
    enable(runtime, apply=True)
    activation.disable(runtime)
    assert not cloud_status(runtime, ROOT)[0]
    activation.disable(runtime)


def test_a_recorded_activation_with_one_proof_is_not_enough(runtime: Path) -> None:
    write_activation(runtime, {"privacy_filter": "2026-10-09T10:00:00Z"})
    assert not cloud_status(runtime, ROOT)[0]


# -- online check -------------------------------------------------------------------
def test_the_online_check_reads_the_real_limit_of_the_key(runtime: Path) -> None:
    activation.set_key(ROOT, runtime, KEY)
    seen: list[tuple[str, str]] = []

    def fetch(base_url: str, key: str) -> dict[str, Any]:
        seen.append((base_url, key))
        return {"limit": 10, "usage": 0.5}

    checks, activated = enable(runtime, verify_online=True, fetch=fetch, apply=True)
    assert not failed(checks) and activated and seen == [("https://openrouter.ai/api/v1", KEY)]
    assert read_activation(runtime)["declared"]["verified_online"] is True


@pytest.mark.parametrize(
    "info", [{"limit": None}, {"limit": 0}, {"limit": True}, {"limit": 50}, {}],
)
def test_a_key_without_limit_or_above_the_declared_one_is_refused_online(
    runtime: Path, info: dict[str, Any]
) -> None:
    activation.set_key(ROOT, runtime, KEY)
    checks, activated = enable(
        runtime, verify_online=True, fetch=lambda *_: info, apply=True)
    assert failed(checks) == ["limite de clé (en ligne)"] and not activated


def test_an_unreachable_provider_blocks_only_the_online_check(runtime: Path) -> None:
    activation.set_key(ROOT, runtime, KEY)

    def down(*_: Any) -> dict[str, Any]:
        raise OSError("réseau coupé")

    checks, activated = enable(runtime, verify_online=True, fetch=down, apply=True)
    assert failed(checks) == ["limite de clé (en ligne)"] and not activated
    assert KEY not in checks[-1].detail


# -- service unit -------------------------------------------------------------------
def test_the_unit_runs_the_gateway_with_the_managed_interpreter(
    runtime: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    units = tmp_path_factory.mktemp("units")
    unit = activation.render_unit(ROOT, runtime, units)
    text = unit.read_text()
    assert text.startswith("# Managed by OPENCLAW_LOCAL_FEDORA")
    assert f"ExecStart={runtime}/runtime/venv/bin/python -m clawfedora.cloud_gateway" in text
    assert "NoNewPrivileges=true" in text and "UMask=0077" in text
    assert KEY not in text and "sk-or" not in text
    unit.write_text("[Service]\nExecStart=/bin/true\n")
    with pytest.raises(ValueError, match="non gérée"):
        activation.render_unit(ROOT, runtime, units)


def test_the_unit_refuses_an_unmanaged_runtime_and_unsafe_paths(
    tmp_path_factory: pytest.TempPathFactory, runtime: Path
) -> None:
    unmanaged = tmp_path_factory.mktemp("unmanaged")
    with pytest.raises(ValueError, match="runtime"):
        activation.render_unit(ROOT, unmanaged, unmanaged / "units")
    with pytest.raises(ValueError, match="chemins"):
        activation.render_unit(ROOT, runtime, Path("/tmp/with space/units"))


# -- command line -------------------------------------------------------------------
def run(runtime: Path, *args: str) -> int:
    return cloud_cli.main(["--root", str(ROOT), "--runtime-root", str(runtime), *args])


def test_the_command_line_reads_the_key_from_the_environment_not_the_arguments(
    runtime: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(cloud_cli.KEY_ENVIRONMENT, KEY)
    assert run(runtime, "set-key") == 0
    assert run(runtime, "enable", "--key-limit-usd", "12", "--confirm-prepaid") == 0
    assert not cloud_status(runtime, ROOT)[0]
    assert run(runtime, "enable", "--key-limit-usd", "12", "--confirm-prepaid", "--apply") == 0
    assert cloud_status(runtime, ROOT)[0]
    capsys.readouterr()
    assert run(runtime, "status") == 0
    out = capsys.readouterr().out
    assert "ready=1" in out and "level=ok" in out and KEY not in out
    assert activation.fingerprint(KEY) in out
    assert run(runtime, "disable") == 0 and not cloud_status(runtime, ROOT)[0]


def test_the_command_line_refuses_to_enable_when_a_check_fails(
    runtime: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(runtime, "enable", "--key-limit-usd", "12", "--confirm-prepaid", "--apply") == 2
    out = capsys.readouterr().out
    assert "ÉCHEC" in out and "cloud reste désactivé" in out
    assert not cloud_status(runtime, ROOT)[0]


def test_reconciling_with_the_invoice_can_exhaust_the_month(
    runtime: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(runtime, "reconcile", "--eur", "21") == 0
    out = capsys.readouterr().out
    assert "spent_eur=21.00" in out and "level=warning" in out
    assert run(runtime, "reconcile", "--eur", "25.5") == 0
    assert "level=exhausted" in capsys.readouterr().out
    assert run(runtime, "reconcile", "--eur", "-1") == 2
