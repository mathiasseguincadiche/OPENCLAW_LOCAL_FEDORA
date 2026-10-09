"""Apprendre (cloud) and Travail (local) modes of the chat gateway."""

from __future__ import annotations

import json
import random
import string
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from clawfedora.cloud_state import CLOUD_STATE
from clawfedora.webui_bridge import (
    CLOUD_BANNER,
    CLOUD_MODEL_IDS,
    MODEL_IDS,
    STICKY_MARKER,
    chat_prompt,
    local_sticky,
    make_server,
    strip_banners,
)

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "b" * 64
GH = "ghp_" + "".join(random.Random(11).choices(string.ascii_letters + string.digits, k=36))


class Runner:
    """Records every call; the cloud route can be made to fail like a refused gateway."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.calls: list[tuple[str, str, str]] = []
        self.cloud_error: Exception | None = None
        self.local_error: Exception | None = None

    def __call__(
        self, role: str, prompt: str, session: str, *, route: str = "local"
    ) -> dict[str, Any]:
        self.calls.append((route, role, session))
        if route == "cloud":
            if self.cloud_error:
                raise self.cloud_error
            return {"text": "Réponse GLM.", "route": "cloud"}
        if self.local_error:
            raise self.local_error
        return {"text": "Réponse Qwen.", "route": "local"}

    def routes(self) -> list[str]:
        return [call[0] for call in self.calls]

    def gateway_event(self, **record: Any) -> None:
        directory = self.tmp / CLOUD_STATE
        directory.mkdir(parents=True, exist_ok=True)
        import time

        record.setdefault("at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        with (directory / "events.jsonl").open("a") as handle:
            handle.write(json.dumps(record) + "\n")


def ask(server: Any, model: str, *messages: tuple[str, str]) -> tuple[int, dict[str, Any]]:
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    body = {"model": model, "messages": [{"role": r, "content": c} for r, c in messages]}
    connection.request("POST", "/v1/chat/completions", body=json.dumps(body),
                       headers={"Authorization": "Bearer " + TOKEN,
                                "Content-Type": "application/json"})
    response = connection.getresponse()
    return response.status, json.loads(response.read())


def models(server: Any) -> dict[str, str]:
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    connection.request("GET", "/v1/models", headers={"Authorization": "Bearer " + TOKEN})
    data = json.loads(connection.getresponse().read())["data"]
    return {item["id"]: item["name"] for item in data}


def serve(tmp: Path, runner: Runner, ready: bool) -> Iterator[Any]:
    (tmp / "state").mkdir(exist_ok=True)
    server = make_server(ROOT, tmp, TOKEN, 0, runner=runner, cloud_ready=lambda: ready)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02},
                     daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def cloud(tmp_path: Path) -> Iterator[tuple[Any, Runner]]:
    runner = Runner(tmp_path)
    yield next(serve(tmp_path, runner, True)), runner


def content(answer: dict[str, Any]) -> str:
    return str(answer["choices"][0]["message"]["content"])


def test_without_the_cloud_only_the_seven_local_roles_are_listed_and_unchanged(
    tmp_path: Path,
) -> None:
    runner = Runner(tmp_path)
    server = next(serve(tmp_path, runner, False))
    listed = models(server)
    assert list(listed) == list(MODEL_IDS) and not any("local" in n.lower() for n in listed.values())
    status, _ = ask(server, CLOUD_MODEL_IDS[0], ("user", "Bonjour"))
    assert status == 400 and runner.calls == []
    status, answer = ask(server, MODEL_IDS[0], ("user", "Bonjour"))
    assert status == 200 and content(answer) == "Réponse Qwen." and runner.routes() == ["local"]


def test_with_the_cloud_each_role_is_offered_in_both_modes(cloud: tuple[Any, Runner]) -> None:
    server, _ = cloud
    listed = models(server)
    assert list(listed) == [*MODEL_IDS, *CLOUD_MODEL_IDS]
    assert listed[MODEL_IDS[0]].endswith("· local")
    assert listed[CLOUD_MODEL_IDS[0]].endswith("· cloud (GLM)")


def test_a_cloud_model_answers_in_the_cloud_with_a_visible_provenance(
    cloud: tuple[Any, Runner],
) -> None:
    server, runner = cloud
    status, answer = ask(server, CLOUD_MODEL_IDS[0], ("user", "Explique terraform plan"))
    assert status == 200 and content(answer).startswith(CLOUD_BANNER)
    assert content(answer).endswith("Réponse GLM.") and runner.routes() == ["cloud"]


def test_a_local_model_never_uses_the_cloud_even_when_it_is_activated(
    cloud: tuple[Any, Runner],
) -> None:
    server, runner = cloud
    status, answer = ask(server, MODEL_IDS[0], ("user", "Bonjour"))
    assert status == 200 and content(answer) == "Réponse Qwen." and runner.routes() == ["local"]


def test_a_secret_moves_the_conversation_to_local_before_anything_is_sent(
    cloud: tuple[Any, Runner],
) -> None:
    server, runner = cloud
    status, answer = ask(server, CLOUD_MODEL_IDS[0], ("user", "voici ma clé " + GH))
    text = content(answer)
    assert status == 200 and runner.routes() == ["local"]
    assert text.startswith(STICKY_MARKER) and "jeton d'accès" in text and GH not in text
    assert text.endswith("Réponse Qwen.")


def test_a_conversation_moved_to_local_stays_local(cloud: tuple[Any, Runner]) -> None:
    server, runner = cloud
    _, first = ask(server, CLOUD_MODEL_IDS[0], ("user", "ma clé " + GH))
    history = [("user", "bonjour"), ("assistant", content(first)), ("user", "et maintenant ?")]
    assert local_sticky([{"role": r, "content": c} for r, c in history])
    # The user still picks the cloud model, and the secret is long gone from the history.
    _, second = ask(server, CLOUD_MODEL_IDS[0], *history)
    assert runner.routes() == ["local", "local"]
    assert content(second).startswith(STICKY_MARKER)
    # Each new answer repeats the marker, so the stickiness survives history trimming.
    _, third = ask(server, CLOUD_MODEL_IDS[0], *history, ("assistant", content(second)),
                   ("user", "encore"))
    assert runner.routes() == ["local"] * 3 and content(third).startswith(STICKY_MARKER)


def test_a_secret_hidden_in_the_added_context_is_also_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from clawfedora import webui_bridge

    runner = Runner(tmp_path)
    server = next(serve(tmp_path, runner, True))
    monkeypatch.setattr(webui_bridge, "mentor_context", lambda _runtime: "Note: token=" + GH)
    status, answer = ask(server, CLOUD_MODEL_IDS[0], ("user", "Bonjour"))
    assert status == 200 and runner.routes() == ["local"]
    assert content(answer).startswith(STICKY_MARKER)


def test_a_gateway_block_found_after_the_fact_also_moves_the_conversation_to_local(
    cloud: tuple[Any, Runner],
) -> None:
    """A secret in a tool result is invisible to the chat gateway but not to the cloud gateway."""
    server, runner = cloud
    runner.cloud_error = ValueError("OpenClaw a échoué (code=1)")
    original = runner.__call__

    def failing(role: str, prompt: str, session: str, *, route: str = "local") -> dict[str, Any]:
        if route == "cloud":
            runner.gateway_event(decision="blocked", categories=["token"])
        return original(role, prompt, session, route=route)

    server.runner = failing  # type: ignore[assignment]
    status, answer = ask(server, CLOUD_MODEL_IDS[0], ("user", "lis le fichier .env"))
    text = content(answer)
    assert status == 200 and text.startswith(STICKY_MARKER) and "jeton d'accès" in text
    assert runner.routes() == ["cloud", "local"] and text.endswith("Réponse Qwen.")


@pytest.mark.parametrize(
    ("decision", "reason"),
    [("budget_refused", "plafond du budget cloud"), ("upstream_unreachable", "fournisseur cloud"),
     ("upstream_error", "fournisseur cloud"), (None, "le cloud est indisponible")],
)
def test_other_cloud_failures_fall_back_to_local_visibly_without_sticking(
    cloud: tuple[Any, Runner], decision: str | None, reason: str
) -> None:
    server, runner = cloud
    runner.cloud_error = ValueError("OpenClaw a échoué (code=1)")
    original = runner.__call__

    def failing(role: str, prompt: str, session: str, *, route: str = "local") -> dict[str, Any]:
        if route == "cloud" and decision:
            runner.gateway_event(decision=decision)
        return original(role, prompt, session, route=route)

    server.runner = failing  # type: ignore[assignment]
    status, answer = ask(server, CLOUD_MODEL_IDS[0], ("user", "Bonjour"))
    text = content(answer)
    assert status == 200 and text.startswith("💻 *Réponse locale") and reason in text
    assert STICKY_MARKER not in text and text.endswith("Réponse Qwen.")
    # Not sticky: the next question tries the cloud again.
    runner.cloud_error = None
    _, again = ask(server, CLOUD_MODEL_IDS[0], ("user", "Bonjour"), ("assistant", text),
                   ("user", "suite"))
    assert runner.routes()[-1] == "cloud" and content(again).startswith(CLOUD_BANNER)


def test_the_fallback_runs_in_a_new_session_and_a_double_failure_is_reported(
    cloud: tuple[Any, Runner],
) -> None:
    server, runner = cloud
    runner.cloud_error = RuntimeError("boom")
    ask(server, CLOUD_MODEL_IDS[0], ("user", "Bonjour"))
    (_, _, cloud_session), (_, _, local_session) = runner.calls
    assert cloud_session != local_session
    runner.local_error = ValueError("Ollama divergent du contrat")
    status, answer = ask(server, CLOUD_MODEL_IDS[0], ("user", "Bonjour"))
    assert status == 409 and "Ollama" in json.dumps(answer)


def test_banners_are_not_fed_back_to_the_model() -> None:
    assert strip_banners(CLOUD_BANNER + "\n\nRéponse") == "Réponse"
    assert strip_banners("💻 *Réponse locale : x.*\n\nRéponse") == "Réponse"
    assert strip_banners(STICKY_MARKER + " : x.\n\nRéponse") == "Réponse"
    assert strip_banners("Réponse normale\n\nsuite") == "Réponse normale\n\nsuite"
    payload = {"model": CLOUD_MODEL_IDS[0], "messages": [
        {"role": "assistant", "content": CLOUD_BANNER + "\n\nVoici la réponse."},
        {"role": "user", "content": "merci"}]}
    _, prompt = chat_prompt(payload, allow_cloud=True)
    assert "Voici la réponse." in prompt and "GLM-5.3" not in prompt
    with pytest.raises(ValueError):
        chat_prompt(payload, allow_cloud=False)


def test_only_the_assistant_can_carry_the_marker() -> None:
    assert not local_sticky([{"role": "user", "content": STICKY_MARKER + " pour rire"}])
    assert not local_sticky([{"role": "assistant", "content": "texte " + STICKY_MARKER}])
