"""The budget never undercounts: reserve before, settle after, keep what is uncertain."""

from __future__ import annotations

import json
import stat
import threading
import time
from pathlib import Path

import pytest

from clawfedora.cloud_budget import BudgetRefused, Ledger, load_ledger, month_key

ROOT = Path(__file__).resolve().parents[1]
OCT = time.mktime(time.strptime("2026-10-15 12:00", "%Y-%m-%d %H:%M")) - time.timezone
NOV = OCT + 20 * 86400
USAGE = {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500, "cost": 0.0004}


class Clock:
    def __init__(self, now: float = OCT) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def ledger(tmp_path: Path, clock: Clock) -> Ledger:
    (tmp_path / "state").mkdir()
    return load_ledger(tmp_path, ROOT, clock)


def lines(ledger: Ledger, month: str = "2026-10") -> list[dict[str, object]]:
    return [json.loads(line) for line in ledger.path(month).read_text().splitlines()]


def test_a_reservation_precedes_the_call_and_the_journal_is_private(ledger: Ledger) -> None:
    held = ledger.reserve(input_tokens=1000, max_output_tokens=4096)
    (record,) = lines(ledger)
    assert record["k"] == "reserve" and record["max_output_tokens"] == 4096
    # 1000 tokens in at 0.25 $/M + 4096 out at 0.75 $/M, worst case.
    assert record["est_usd"] == pytest.approx(0.00025 + 0.003072)
    assert stat.S_IMODE(ledger.path("2026-10").stat().st_mode) == 0o600
    assert ledger.summary().pending == 1
    held.settle(USAGE, "ok")


def test_the_real_cost_replaces_the_estimate_and_is_converted_in_euros(ledger: Ledger) -> None:
    ledger.reserve(input_tokens=1000, max_output_tokens=4096).settle(USAGE, "ok")
    summary = ledger.summary()
    assert (summary.calls_ok, summary.pending) == (1, 0)
    assert summary.spent_usd == pytest.approx(0.0004)
    # The pessimistic factor of the policy covers exchange, credit fees and VAT.
    assert summary.spent_eur == pytest.approx(0.0004 * 1.3)
    assert summary.effective_eur == summary.spent_eur and summary.cap_eur == 25


def test_without_a_cost_the_tokens_are_priced_with_the_policy(ledger: Ledger) -> None:
    usage = {"prompt_tokens": 2_000_000, "completion_tokens": 1_000_000}
    ledger.reserve(input_tokens=10, max_output_tokens=10).settle(usage, "ok")
    assert ledger.summary().spent_usd == pytest.approx(2 * 0.25 + 1 * 0.75)


def test_only_a_refused_call_is_released_everything_uncertain_keeps_its_estimate(
    ledger: Ledger,
) -> None:
    estimate = ledger.estimate_usd(1000, 4096)
    ledger.reserve(input_tokens=1000, max_output_tokens=4096).settle(None, "failed")
    assert ledger.summary().spent_usd == 0 and ledger.summary().calls_failed == 1
    ledger.reserve(input_tokens=1000, max_output_tokens=4096).settle(None, "interrupted")
    ledger.reserve(input_tokens=1000, max_output_tokens=4096).settle(None, "ok")  # no usage
    ledger.reserve(input_tokens=1000, max_output_tokens=4096)  # never settled: a crash
    summary = ledger.summary()
    assert (summary.calls_uncertain, summary.pending) == (2, 1)
    assert summary.spent_usd == pytest.approx(3 * estimate)


def test_a_call_that_would_pass_the_cap_is_refused_and_leaves_no_trace(ledger: Ledger) -> None:
    # 36 M input tokens = 9 $ = 11.70 € of worst case per call.
    ledger.reserve(input_tokens=36_000_000, max_output_tokens=0)
    ledger.reserve(input_tokens=36_000_000, max_output_tokens=0)
    before = ledger.path("2026-10").read_text()
    with pytest.raises(BudgetRefused, match="plafond mensuel atteint: 23.40 € sur 25 €"):
        ledger.reserve(input_tokens=36_000_000, max_output_tokens=0)
    assert ledger.path("2026-10").read_text() == before
    # A small call still fits in what remains.
    ledger.reserve(input_tokens=1000, max_output_tokens=4096)


def test_the_cap_holds_under_concurrency(ledger: Ledger) -> None:
    results: list[bool] = []

    def attempt() -> None:
        try:
            ledger.reserve(input_tokens=4_000_000, max_output_tokens=0)  # 1 $ = 1.30 €
            results.append(True)
        except BudgetRefused:
            results.append(False)

    threads = [threading.Thread(target=attempt) for _ in range(60)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    # 25 / 1.30 = 19.2: exactly nineteen calls fit, never one more.
    assert results.count(True) == 19 and results.count(False) == 41
    assert ledger.summary().effective_eur <= 25


def test_a_new_month_starts_a_new_journal_and_keeps_the_old_one(
    ledger: Ledger, clock: Clock
) -> None:
    ledger.reserve(input_tokens=60_000_000, max_output_tokens=0).settle(
        {"cost": 9.0}, "ok")
    assert month_key(clock.now) == "2026-10" and ledger.summary().effective_eur > 11
    clock.now = NOV
    assert month_key(clock.now) == "2026-11" and ledger.summary().effective_eur == 0
    ledger.reserve(input_tokens=1000, max_output_tokens=10)
    assert ledger.path("2026-11").exists() and ledger.summary("2026-10").calls_ok == 1


def test_a_real_invoice_raises_the_floor_of_what_is_counted(ledger: Ledger) -> None:
    ledger.reserve(input_tokens=1000, max_output_tokens=10).settle(USAGE, "ok")
    assert ledger.summary().billed_eur == 0
    ledger.record_invoice(24.9, note="relevé OpenRouter")
    summary = ledger.summary()
    # The statement says more than the ledger: the statement wins, so the cap is real euros.
    assert summary.billed_eur == 24.9 and summary.effective_eur == 24.9
    with pytest.raises(BudgetRefused):
        ledger.reserve(input_tokens=6_666_667, max_output_tokens=0)  # 1.30 € more
    ledger.record_invoice(2.0)  # the latest statement is the truth, even if lower
    assert ledger.summary().effective_eur == 2.0
    for bad in (-1, 1001):
        with pytest.raises(ValueError):
            ledger.record_invoice(bad)


def test_an_underestimate_is_counted_at_its_real_cost_and_flagged(ledger: Ledger) -> None:
    held = ledger.reserve(input_tokens=1, max_output_tokens=1)
    held.settle({"cost": 0.5}, "ok")
    settle = lines(ledger)[-1]
    assert settle["overrun"] is True and ledger.summary().spent_usd == pytest.approx(0.5)


def test_settling_twice_counts_once(ledger: Ledger) -> None:
    held = ledger.reserve(input_tokens=1000, max_output_tokens=10)
    held.settle(USAGE, "ok")
    held.settle({"cost": 99}, "ok")
    assert len(lines(ledger)) == 2 and ledger.summary().spent_usd == pytest.approx(0.0004)


def test_a_write_cut_short_by_a_crash_is_ignored_any_other_damage_stops_the_cloud(
    ledger: Ledger,
) -> None:
    ledger.reserve(input_tokens=1000, max_output_tokens=10).settle(USAGE, "ok")
    path = ledger.path("2026-10")
    with path.open("a") as handle:
        handle.write('{"k": "reserve", "id": "x", "est_u')  # no newline: cut short
    assert ledger.summary().calls_ok == 1
    ledger.reserve(input_tokens=1000, max_output_tokens=10)
    text = path.read_text().replace('"k": "settle"', "BROKEN", 1)
    path.write_text(text)
    with pytest.raises(BudgetRefused, match="journal du budget illisible"):
        ledger.reserve(input_tokens=1000, max_output_tokens=10)


def test_levels_follow_the_alert_ratio(ledger: Ledger) -> None:
    assert ledger.summary().level(ledger.alert_ratio) == "ok"
    ledger.record_invoice(20.0)
    assert ledger.summary().level(0.8) == "warning"
    ledger.record_invoice(25.0)
    assert ledger.summary().level(0.8) == "exhausted"
    assert ledger.summary().remaining_eur == 0
