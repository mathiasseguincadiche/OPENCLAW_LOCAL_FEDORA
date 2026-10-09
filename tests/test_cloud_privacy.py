"""The filter blocks credentials and personal terms, and lets teaching examples through."""

from __future__ import annotations

import random
import string
from pathlib import Path
from typing import Any

import pytest

from clawfedora.agents import effective_instructions
from clawfedora.cloud_privacy import PrivacyFilter, describe

ROOT = Path(__file__).resolve().parents[1]
RANDOM = random.Random(20261009)


def rnd(length: int, alphabet: str = string.ascii_letters + string.digits) -> str:
    return "".join(RANDOM.choice(alphabet) for _ in range(length))


def body(*messages: tuple[str, str]) -> dict[str, Any]:
    return {"messages": [{"role": role, "content": text} for role, text in messages]}


def categories(request: dict[str, Any], filter_: PrivacyFilter | None = None) -> set[str]:
    return {item.category for item in (filter_ or PrivacyFilter()).scan_request(request)}


# Built at run time: this file must not contain anything that looks like a real credential.
SECRETS = {
    "private_key": "-----BEGIN " + "OPENSSH PRIVATE KEY-----\n" + rnd(60),
    "cloud_credential": "aws_access_key_id = AKIA"
    + rnd(16, string.ascii_uppercase + string.digits),
    "token": "export GH=" + "ghp_" + rnd(36),
    "connection_string": "postgres://admin:" + rnd(14) + "@db.internal:5432/app",
    "secret_assignment": 'client_secret = "' + rnd(24) + '"',
    "subscription_id": 'subscription_id = "' + "7f3c9a42-1d5e-4b8a-9c60-2e8f4a1b6d73" + '"',
}


@pytest.mark.parametrize("category", sorted(SECRETS))
def test_each_kind_of_credential_is_blocked_wherever_it_travels(category: str) -> None:
    secret = SECRETS[category]
    # In the user's message, in the history, in a system prompt and in a tool result.
    for role in ("user", "assistant", "system", "tool"):
        found = categories(body(("user", "bonjour"), (role, "voici:\n" + secret)))
        assert category in found, (role, found)


def test_a_secret_in_a_tool_call_argument_is_blocked() -> None:
    request = {
        "messages": [
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "web_fetch",
                              "arguments": '{"url": "' + SECRETS["token"] + '"}'}}
            ]}
        ]
    }
    assert "token" in categories(request)


def test_findings_never_contain_the_secret() -> None:
    request = body(("user", SECRETS["token"] + " " + SECRETS["secret_assignment"]))
    findings = PrivacyFilter().scan_request(request)
    rendered = repr(findings) + describe(findings)
    for secret in SECRETS.values():
        assert secret not in rendered
    token_value = SECRETS["token"].split("=", 1)[1]
    assert token_value not in rendered


def test_non_text_content_is_refused() -> None:
    request = {"messages": [{"role": "user", "content": [
        {"type": "text", "text": "voir"}, {"type": "image_url", "image_url": {"url": "data:..."}}]}]}
    assert categories(request) == {"non_text_content"}
    assert categories({"messages": "texte"}) == {"non_text_content"}


TEACHING = [
    # documentation ranges, private addresses, example hosts
    'resource "azurerm_virtual_network" "vnet" { address_space = ["10.0.0.0/16"] }',
    "ansible_host: 192.168.1.10   # puis 203.0.113.7 et 198.51.100.4, https://example.com/api",
    # templated or referenced secrets
    'administrator_login_password = var.admin_password',
    'client_secret = var.client_secret',
    'ansible_password: "{{ vault_admin_password }}"',
    'password = "${data.azurerm_key_vault_secret.db.value}"',
    "- name: Login\n  env:\n    TOKEN: ${{ secrets.DEPLOY_TOKEN }}",
    'api_key = os.environ["API_KEY"]',
    "token: $CI_JOB_TOKEN",
    # tutorial words and low-entropy sample values
    'password = "P@ssw0rd123!"',
    'admin_password: "ChangeMe123"',
    "postgres://user:password@localhost:5432/app",
    "mysql://root:root@127.0.0.1/db",
    # canonical documented samples
    "aws_access_key_id = AKIAIOSFODNN7EXAMPLE",
    "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    'subscription_id = "00000000-0000-0000-0000-000000000000"',
    '/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/rg',
    'tenant_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"',
    # prose that merely talks about secrets
    "Ne mets jamais un mot de passe, un jeton ou une clé privée dans le dépôt Git.",
    "Un secret est stocké dans Key Vault ; le token est lu à l'exécution par la CI.",
    "terraform plan -out=tfplan && terraform apply tfplan",
    "ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519   # génère la clé, ne la partage pas",
    "git config user.email 'moi@example.com'",
    "sha256: 9b74c9897bac770ffc029102a200c5de",
]


@pytest.mark.parametrize("text", TEACHING)
def test_teaching_examples_are_not_blocked(text: str) -> None:
    assert categories(body(("user", text))) == set(), text


@pytest.mark.parametrize(
    "role",
    ["chef-operations", "expert-recherche", "architecte-solutions", "ingenieur-devops",
     "ingenieur-securite", "redacteur-pedagogique", "auditeur-qualite"],
)
def test_the_real_role_instructions_are_not_blocked(role: str) -> None:
    prompt = effective_instructions(ROOT, role)
    assert categories(body(("system", prompt))) == set()


def test_the_personal_denylist_blocks_literals_and_patterns(tmp_path: Path) -> None:
    path = tmp_path / "denylist.txt"
    path.write_text("# mes termes\nAcme Industrie\nre:srv-[a-z]{3}-\\d+\nab\n")
    filter_ = PrivacyFilter(path)
    assert categories(body(("user", "config de ACME industrie ici")), filter_) == {"denylist"}
    assert categories(body(("user", "hôte srv-prd-042")), filter_) == {"denylist"}
    # Terms under three characters and comments are ignored.
    assert categories(body(("user", "ab et # mes termes")), filter_) == set()
    # The file is re-read when it changes.
    path.write_text("nouveau-client\n")
    assert categories(body(("user", "pour nouveau-client")), filter_) == {"denylist"}
    assert categories(body(("user", "Acme Industrie")), filter_) == set()


def test_a_missing_denylist_blocks_nothing_by_itself(tmp_path: Path) -> None:
    assert categories(body(("user", "bonjour")), PrivacyFilter(tmp_path / "absent.txt")) == set()


def test_description_names_the_kind_and_the_place_without_values() -> None:
    findings = PrivacyFilter().scan_request(body(("user", "x"), ("tool", SECRETS["token"])))
    text = describe(findings)
    assert "jeton d'accès" in text and "résultat d'outil" in text


def test_a_history_embedded_as_json_is_scanned_in_its_plain_form() -> None:
    """The chat gateway sends the history as a JSON string: escapes must not hide a secret."""
    import json

    history = json.dumps(
        [{"role": "user", "content": SECRETS["secret_assignment"] + "\n" + SECRETS["private_key"]}],
        ensure_ascii=False,
    )
    assert "secret_assignment" in categories(body(("user", "Historique:\n" + history)))
    assert "private_key" in categories(body(("user", history)))
    # Twice-escaped content too, and text with unrelated backslashes terminates.
    twice = json.dumps(history)
    assert "secret_assignment" in categories(body(("user", twice)))
    assert categories(body(("user", r"grep -E '\d+\s*\w' fichier"))) == set()
