"""Privacy filter for everything that would leave for the cloud.

It scans the whole request body of the gateway: system prompt, history, added context, tool
calls and tool results. It looks for credentials and for the user's own sensitive terms; it
never stores or returns the matched value, only a category and where it was found.

Limits, stated plainly: a filter cannot recognise what is confidential without looking like a
secret (an employer's configuration, an internal server name). That is the job of the local
"Travail" mode and of the personal denylist, not of pattern matching.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Finding:
    category: str
    where: str


LABELS = {
    "private_key": "clé privée",
    "cloud_credential": "identifiant ou clé d'un service cloud",
    "token": "jeton d'accès",
    "connection_string": "chaîne de connexion ou identifiants dans une URL",
    "secret_assignment": "valeur secrète affectée à un mot de passe, une clé ou un jeton",
    "subscription_id": "identifiant réel d'abonnement, de tenant ou de service",
    "denylist": "terme de votre liste personnelle de termes sensibles",
    "non_text_content": "contenu non textuel",
}

# Tokens whose format alone identifies them. Documented samples (EXAMPLE, xxxx) are allowed.
_FORMATS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PGP )?PRIVATE KEY(?: BLOCK)?-----")),
    ("private_key", re.compile(r"client-key-data:\s*[A-Za-z0-9+/=]{40,}")),
    ("cloud_credential", re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA)[0-9A-Z]{16}\b")),
    ("cloud_credential", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("cloud_credential", re.compile(r"AccountKey=[A-Za-z0-9+/=]{40,}")),
    ("cloud_credential", re.compile(r"[?&]sig=[A-Za-z0-9%]{30,}")),
    ("cloud_credential", re.compile(r"\b[A-Za-z0-9_.~\-]{3}8Q~[A-Za-z0-9_.~\-]{30,}")),
    ("token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b")),
    ("token", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}")),
    ("token", re.compile(r"\bsk-or-v1-[A-Za-z0-9]{24,}")),
    ("token", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("token", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    ("token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("token", re.compile(
        r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
)
_SAMPLE_MARKERS = ("example", "xxxx", "your-", "your_", "<", "${", "{{", "redacted", "placeholder")

_ASSIGNMENT = re.compile(
    r"""(?ix)
    \b(?P<key>[A-Za-z0-9_.\-]*(?:password|passwd|pwd|secret|token|api[_\-]?key|apikey|
        access[_\-]?key|private[_\-]?key|client[_\-]?secret)[A-Za-z0-9_.\-]*)
    \s*(?:=|:|=>)\s*["']?(?P<value>[^\s"'`,;}\]]{8,})
    """
)
_URL_CREDENTIALS = re.compile(r"\b[a-z][a-z0-9+.\-]*://[^/\s:@]+:(?P<value>[^/\s@]{6,})@")
_GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_ID_CONTEXT = re.compile(
    rf"""(?ix)
    (?:(?:subscription|tenant|object|principal|client)[_\- ]?id|/subscriptions/|/tenants/)
    ["']?\s*[=:]?\s*["']?(?P<guid>{_GUID})
    """
)
_TEMPLATED = re.compile(
    r"^(?:var|local|data|module|env|secrets|vars|vault|lookup|input)[.\[(]|\$\{|\$\(|\{\{|<|%\(|\$[A-Za-z_]"
)
_PLACEHOLDER_WORDS = (
    "example", "changeme", "change-me", "placeholder", "dummy", "sample", "redacted",
    "yourpassword", "mypassword", "xxxx", "****", "todo", "fixme", "notasecret",
)


_JSON_ESCAPES = re.compile(r'\\(?:["\\/nrt])')
_UNESCAPED = {'\\"': '"', "\\\\": "\\", "\\/": "/", "\\n": "\n", "\\r": "\r", "\\t": "\t"}


def _entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {char: value.count(char) for char in set(value)}
    return -sum(n / len(value) * math.log2(n / len(value)) for n in counts.values())


def looks_secret(value: str, *, strict: bool = True) -> bool:
    """True for a value that looks like a real credential, not a template or a tutorial word."""
    lowered = value.lower()
    if _TEMPLATED.match(value) or any(word in lowered for word in _PLACEHOLDER_WORDS):
        return False
    if len(set(value)) <= 3:
        return False
    if strict:
        return len(value) >= 16 and _entropy(value) >= 3.5
    return len(value) >= 6 and _entropy(value) >= 2.5 and not re.fullmatch(
        r"(?i)(password|passwd|pass|secret|token|admin|root|user|test|guest)\d*", value
    )


def _placeholder_guid(guid: str) -> bool:
    """Zeros, repeated characters, and the sequential samples of vendor documentation."""
    digits = guid.replace("-", "").lower()
    return len(set(digits)) <= 3 or "12345678" in digits or "abcdef" in digits


def _texts(message: dict[str, Any], index: int) -> Iterable[tuple[str, str]]:
    role = str(message.get("role", "?"))
    where = f"messages[{index}].{role}"
    content = message.get("content")
    if isinstance(content, str):
        yield where, content
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text" and isinstance(
                part.get("text"), str
            ):
                yield where, part["text"]
            else:
                yield where, "\0non_text"
    elif content is not None:
        yield where, "\0non_text"
    calls = message.get("tool_calls")
    if isinstance(calls, list):
        for call in calls:
            function = call.get("function") if isinstance(call, dict) else None
            if isinstance(function, dict) and isinstance(function.get("arguments"), str):
                yield f"{where}.tool_call", function["arguments"]


class PrivacyFilter:
    """Stateless apart from the optional personal denylist, re-read when its file changes."""

    def __init__(self, denylist: Path | Callable[[], list[str]] | None = None) -> None:
        self._denylist = denylist
        self._cache: tuple[tuple[int, int], list[str]] | None = None

    def _terms(self) -> list[str]:
        source = self._denylist
        if source is None:
            return []
        if callable(source):
            return source()
        try:
            stat = source.stat()
            key = (stat.st_mtime_ns, stat.st_size)
            if self._cache and self._cache[0] == key:
                return self._cache[1]
            lines = source.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        terms = [
            line.strip()
            for line in lines
            if len(line.strip()) >= 3 and not line.startswith("#")
        ]
        self._cache = (key, terms)
        return terms

    def scan_text(self, text: str, where: str) -> list[Finding]:
        if text == "\0non_text":
            return [Finding("non_text_content", where)]
        found: set[str] = set()
        # A history embedded as JSON escapes quotes and line breaks: scan the plain form too.
        if "\\" in text:
            plain = _JSON_ESCAPES.sub(lambda m: _UNESCAPED[m.group(0)], text)
            if plain != text:
                found.update(item.category for item in self.scan_text(plain, where))
        for category, pattern in _FORMATS:
            for match in pattern.finditer(text):
                if not any(marker in match.group(0).lower() for marker in _SAMPLE_MARKERS):
                    found.add(category)
        for match in _ASSIGNMENT.finditer(text):
            if looks_secret(match.group("value")):
                found.add("secret_assignment")
        for match in _URL_CREDENTIALS.finditer(text):
            if looks_secret(match.group("value"), strict=False):
                found.add("connection_string")
        for match in _ID_CONTEXT.finditer(text):
            if not _placeholder_guid(match.group("guid")):
                found.add("subscription_id")
        lowered = text.lower()
        for term in self._terms():
            if term.startswith("re:"):
                try:
                    if re.search(term[3:200], text, re.IGNORECASE):
                        found.add("denylist")
                except re.error:
                    continue
            elif term.lower() in lowered:
                found.add("denylist")
        return [Finding(category, where) for category in sorted(found)]

    def scan_request(self, body: dict[str, Any]) -> list[Finding]:
        """Every message is scanned: nothing is trusted because of who wrote it."""
        messages = body.get("messages")
        if not isinstance(messages, list):
            return [Finding("non_text_content", "messages")]
        findings: list[Finding] = []
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                findings.append(Finding("non_text_content", f"messages[{index}]"))
                continue
            for where, text in _texts(message, index):
                findings.extend(self.scan_text(text, where))
        return list(dict.fromkeys(findings))


def describe(findings: list[Finding]) -> str:
    """Human summary of what was found and where. Never contains the matched values."""
    if not findings:
        return ""
    parts = []
    for finding in findings:
        where = "résultat d'outil" if ".tool" in finding.where else (
            "historique ou message" if "user" in finding.where or "assistant" in finding.where
            else "consignes ou contexte"
        )
        parts.append(f"{LABELS.get(finding.category, finding.category)} ({where})")
    return "; ".join(dict.fromkeys(parts))
