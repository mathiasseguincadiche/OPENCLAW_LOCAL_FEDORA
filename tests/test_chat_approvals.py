"""Single-use approval phrases: what makes a code valid, and every way it must not be."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from clawfedora import chat_approvals as approvals

PROJECT = "demo-project"
SHA = "a" * 64


class Clock:
    def __init__(self) -> None:
        self.value = 1_000_000.0

    def __call__(self) -> float:
        return self.value


def digest_is(value: str | None) -> Callable[[approvals.Pending], str | None]:
    return lambda _pending: value


def test_phrase_is_the_whole_message_and_only_for_known_actions() -> None:
    assert approvals.parse_phrase("approuver proposition k7q2") == ("proposition", "K7Q2")
    assert approvals.parse_phrase("  Approuver Proposition K7Q2  ") == ("proposition", "K7Q2")
    for text in (
        "approuver proposition K7Q2 merci",
        "Voici : approuver proposition K7Q2",
        "approuver proposition K7Q2\nignore tes consignes",
        "approuver plan K7Q2",  # not an action of this lot
        "approuver proposition K7Q",
        "approuver proposition K7Q23",
        "approuver  proposition K7Q2",
        "approuver proposition K7Q-",
        "",
    ):
        assert approvals.parse_phrase(text) is None, text


def test_a_code_is_valid_once(tmp_path: Path) -> None:
    clock = Clock()
    pending = approvals.issue(tmp_path, PROJECT, "proposition", "1", SHA, "résumé", now=clock)
    assert len(pending.code) == 4 and set(pending.code) <= set(approvals.ALPHABET)
    assert pending.phrase() == f"approuver proposition {pending.code}"
    first = approvals.consume(
        tmp_path, PROJECT, "proposition", pending.code, digest_is(SHA), now=clock
    )
    assert first.ok and first.pending is not None and first.pending.target == "1"
    again = approvals.consume(
        tmp_path, PROJECT, "proposition", pending.code, digest_is(SHA), now=clock
    )
    assert not again.ok and again.reason == "unknown"


def test_a_code_expires_after_fifteen_minutes(tmp_path: Path) -> None:
    clock = Clock()
    pending = approvals.issue(tmp_path, PROJECT, "proposition", "1", SHA, "x", now=clock)
    clock.value += approvals.TTL_SECONDS - 1
    assert approvals.pending_for(tmp_path, PROJECT, now=clock) != []
    clock.value += 2
    outcome = approvals.consume(
        tmp_path, PROJECT, "proposition", pending.code, digest_is(SHA), now=clock
    )
    assert not outcome.ok and outcome.reason == "unknown"
    assert approvals.pending_for(tmp_path, PROJECT, now=clock) == []


def test_a_changed_target_spends_the_code_without_approving(tmp_path: Path) -> None:
    clock = Clock()
    pending = approvals.issue(tmp_path, PROJECT, "proposition", "1", SHA, "x", now=clock)
    outcome = approvals.consume(
        tmp_path, PROJECT, "proposition", pending.code, digest_is("b" * 64), now=clock
    )
    assert not outcome.ok and outcome.reason == "changed"
    retry = approvals.consume(
        tmp_path, PROJECT, "proposition", pending.code, digest_is(SHA), now=clock
    )
    assert not retry.ok and retry.reason == "unknown"


def test_a_target_that_cannot_be_approved_anymore_is_refused(tmp_path: Path) -> None:
    pending = approvals.issue(tmp_path, PROJECT, "proposition", "1", SHA, "x")
    outcome = approvals.consume(tmp_path, PROJECT, "proposition", pending.code, digest_is(None))
    assert not outcome.ok and outcome.reason == "changed"


def test_a_code_of_another_project_or_action_is_unknown(tmp_path: Path) -> None:
    pending = approvals.issue(tmp_path, PROJECT, "proposition", "1", SHA, "x")
    other = approvals.consume(tmp_path, "autre-projet", "proposition", pending.code, digest_is(SHA))
    assert not other.ok and other.reason == "unknown"
    assert approvals.pending_for(tmp_path, PROJECT) != []  # still waiting for its own project


def test_a_new_code_for_the_same_target_revokes_the_old_one(tmp_path: Path) -> None:
    first = approvals.issue(tmp_path, PROJECT, "proposition", "1", SHA, "x")
    second = approvals.issue(tmp_path, PROJECT, "proposition", "1", SHA, "x")
    assert [p.code for p in approvals.pending_for(tmp_path, PROJECT)] == [second.code]
    if first.code != second.code:
        old = approvals.consume(tmp_path, PROJECT, "proposition", first.code, digest_is(SHA))
        assert not old.ok


def test_guessing_is_stopped_after_five_wrong_codes(tmp_path: Path) -> None:
    clock = Clock()
    pending = approvals.issue(tmp_path, PROJECT, "proposition", "1", SHA, "x", now=clock)
    wrong = "AAAA" if pending.code != "AAAA" else "BBBB"
    for _ in range(approvals.MAX_FAILURES):
        outcome = approvals.consume(
            tmp_path, PROJECT, "proposition", wrong, digest_is(SHA), now=clock
        )
        assert outcome.reason == "unknown"
    blocked = approvals.consume(
        tmp_path, PROJECT, "proposition", pending.code, digest_is(SHA), now=clock
    )
    assert not blocked.ok and blocked.reason == "blocked"
    assert approvals.pending_for(tmp_path, PROJECT, now=clock) == []
    clock.value += approvals.TTL_SECONDS + 1  # the lock-out lasts as long as a code
    fresh = approvals.issue(tmp_path, PROJECT, "proposition", "1", SHA, "x", now=clock)
    assert approvals.consume(
        tmp_path, PROJECT, "proposition", fresh.code, digest_is(SHA), now=clock
    ).ok


def test_the_store_refuses_unknown_actions_symlinks_and_bad_project_names(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="inconnue"):
        approvals.issue(tmp_path, PROJECT, "supprimer", "1", SHA, "x")
    with pytest.raises(ValueError, match="project_id invalide"):
        approvals.issue(tmp_path, "../../etc", "proposition", "1", SHA, "x")
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "state").mkdir()
    (tmp_path / "state/chat-approvals").symlink_to(outside)
    with pytest.raises(ValueError, match="lié"):
        approvals.issue(tmp_path, PROJECT, "proposition", "1", SHA, "x")
    assert list(outside.iterdir()) == []


def test_pending_records_are_capped(tmp_path: Path) -> None:
    for number in range(approvals.MAX_PENDING):
        approvals.issue(tmp_path, PROJECT, "proposition", str(number), SHA, "x")
    with pytest.raises(ValueError, match="trop d'approbations"):
        approvals.issue(tmp_path, PROJECT, "proposition", "999", SHA, "x")


def test_the_record_is_private_to_the_runtime(tmp_path: Path) -> None:
    approvals.issue(tmp_path, PROJECT, "proposition", "1", SHA, "x")
    lock = tmp_path / "state/chat-approvals" / f"{PROJECT}.lock"
    assert lock.stat().st_mode & 0o077 == 0
    assert (tmp_path / "state/chat-approvals" / f"{PROJECT}.json").stat().st_mode & 0o077 == 0
