"""Controlled variants of the existing Ollama GPU service configuration.

These are *candidate* profiles, not evidence of Vulkan support or speed.
Only two settings may change; the 32K agent contract and isolation remain intact.
"""
from __future__ import annotations

import argparse
import re
import shlex
import sys

PROFILES: dict[str, tuple[str, str]] = {
    "reference": ("0", "f16"),
    "flash": ("1", "f16"),
    "q8": ("1", "q8_0"),
}
_FIXED = {
    "OLLAMA_HOST": "127.0.0.1:11434",
    "OLLAMA_VULKAN": "1",
    "OLLAMA_NUM_PARALLEL": "1",
    "OLLAMA_MAX_LOADED_MODELS": "1",
    "OLLAMA_MAX_QUEUE": "4",
    "OLLAMA_CONTEXT_LENGTH": "32768",
    "OLLAMA_KEEP_ALIVE": "3m",
    "OLLAMA_NO_CLOUD": "1",
}
_FLASH = "OLLAMA_FLASH_ATTENTION"
_KV = "OLLAMA_KV_CACHE_TYPE"
_TARGETS = {_FLASH, _KV}
_MAX_CONFIG_CHARS = 32000
_ENV_LINE = re.compile(r'^Environment="([A-Z0-9_]+)=([^"\r\n]*)"$')


def _settings(profile: str) -> dict[str, str]:
    if profile not in PROFILES:
        raise ValueError("profil GPU inconnu")
    flash, kv = PROFILES[profile]
    return {_FLASH: flash, _KV: kv}


def _validate_fixed(values: dict[str, str]) -> None:
    if any(values.get(key) != expected for key, expected in _FIXED.items()):
        raise ValueError("contrat Ollama local divergent; réinstaller le profil quotidien")


def patch_config(config: str, profile: str) -> str:
    """Patch only exact managed Environment lines in [Service]."""
    desired = _settings(profile)
    if not config or len(config) > _MAX_CONFIG_CHARS or "\x00" in config:
        raise ValueError("configuration Ollama absente ou trop volumineuse")
    section = ""
    service_count = 0
    values: dict[str, str] = {}
    result: list[str] = []
    for raw in config.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line
            if section == "[Service]":
                service_count += 1
        if section == "[Service]" and line.startswith("Environment"):
            # The generated daily drop-in uses exactly this one-variable syntax.
            # Reject unfamiliar/combined directives instead of rewriting them.
            match = _ENV_LINE.fullmatch(line)
            if match is None:
                raise ValueError("directive Environment non gérée; modification refusée")
            key, value = match.groups()
            if key in values:
                raise ValueError("variable Environment dupliquée")
            values[key] = value
            if key in _TARGETS:
                if value not in ({"0", "1"} if key == _FLASH else {"f16", "q8_0"}):
                    raise ValueError("valeur GPU antérieure inconnue")
                continue
        result.append(raw)
    if service_count != 1 or section != "[Service]":
        raise ValueError("section Service gérée introuvable ou ambiguë")
    _validate_fixed(values)
    if _KV not in values:
        raise ValueError("cache KV géré absent")
    # No custom EnvironmentFile or UnsetEnvironment in the managed unit.
    if any(line.strip().startswith("UnsetEnvironment") for line in result):
        raise ValueError("directive UnsetEnvironment non gérée")
    result.extend(f'Environment="{key}={value}"' for key, value in desired.items())
    return "\n".join(result) + "\n"


def effective_profile(environment: str) -> str:
    """Classify the systemd Environment property, never expose unrelated values.

    This verifies the configured service environment, not that the model/backend
    actually implements Flash Attention or quantised KV.
    """
    if len(environment) > _MAX_CONFIG_CHARS:
        raise ValueError("environnement Ollama trop volumineux")
    values: dict[str, str] = {}
    for item in shlex.split(environment):
        key, sep, value = item.partition("=")
        if not sep:
            raise ValueError("environnement systemd illisible")
        if key in _FIXED or key in _TARGETS:
            if key in values:
                raise ValueError("variable systemd dupliquée")
            values[key] = value
    _validate_fixed(values)
    # An older managed unit may omit Flash Attention; that is NOT proof of off.
    for profile in PROFILES:
        if all(values.get(key) == val for key, val in _settings(profile).items()):
            return profile
    return "unverified"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profils GPU Ollama contrôlés")
    parser.add_argument("action", choices=("patch", "check", "status"))
    parser.add_argument("profile", nargs="?", choices=tuple(PROFILES))
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.read(_MAX_CONFIG_CHARS + 1)
        if args.action == "patch":
            if not args.profile:
                raise ValueError("profil obligatoire")
            sys.stdout.write(patch_config(raw, args.profile))
        else:
            actual = effective_profile(raw)
            if args.action == "check" and actual != args.profile:
                raise ValueError("profil systemd effectif divergent")
            print(f"GPU_PROFILE_CONFIGURED={actual}")
    except (OSError, ValueError) as exc:
        print(f"GPU_PROFILE_REFUSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
