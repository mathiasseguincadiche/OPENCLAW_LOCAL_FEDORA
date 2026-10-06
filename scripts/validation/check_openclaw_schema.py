"""Validate generated configurations with the pinned, real OpenClaw CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from clawfedora.core_config import root_contract
from clawfedora.openclaw_config import build_openclaw_patch, prepare_migration_patch
from clawfedora.version_lock import extract_openclaw_version

repo = Path(__file__).resolve().parents[2]
cli = shutil.which("openclaw")
if not cli:
    raise SystemExit("OpenClaw CLI absent: install the exact pin and Parallel plugin first")
version = subprocess.run([cli, "--version"], capture_output=True, text=True, check=True).stdout
pin = str(root_contract(repo, "runtime_versions.yaml")["openclaw"]["version"])
if extract_openclaw_version(version) != pin:
    raise SystemExit("OpenClaw version differs from the repository pin")
plugin = Path(os.environ["OPENCLAW_SCHEMA_PARALLEL_PATH"]).resolve()
if not (plugin / "openclaw.plugin.json").is_file():
    raise SystemExit("Pinned Parallel plugin absent")
for backend in ("ollama-vulkan", "llama-cpp-vulkan"):
    with tempfile.TemporaryDirectory(prefix="clawfedora-native-schema-") as temporary:
        state = Path(temporary)
        config = build_openclaw_patch(repo, state, backend)
        config["plugins"] = {
            "allow": ["parallel"],
            "load": {"paths": [str(plugin)]},
            "entries": {"parallel": {"enabled": True}},
        }
        path = state / "openclaw.json"
        env = dict(
            os.environ,
            OPENCLAW_STATE_DIR=str(state),
            OPENCLAW_CONFIG_PATH=str(path),
            OLLAMA_API_KEY="ollama-local",
            INTEL_VULKAN_API_KEY="intel-vulkan-local",
        )
        for invalid in (False, True):
            if invalid:
                config["agents"]["defaults"]["pdfMaxBytesMb"] = 50
            path.write_text(json.dumps(config))
            result = subprocess.run(
                [cli, "config", "validate", "--json"],
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            try:
                payload = json.loads(result.stdout)
            except ValueError as exc:
                raise SystemExit(f"Native schema returned no JSON: {result.stderr[-1000:]}") from exc
            if invalid:
                if result.returncode == 0 or payload.get("valid") is not False:
                    raise SystemExit("Regression: native schema accepted the retired PDF key")
            else:
                if result.returncode != 0 or payload.get("valid") is not True:
                    raise SystemExit(f"Native schema rejected {backend}: {payload}")
                blocked = [
                    item
                    for item in payload.get("warnings", [])
                    if "blocked" in str(item).lower() or "not available" in str(item).lower()
                ]
                if blocked:
                    raise SystemExit(f"Plugin validation incomplete: {blocked[:2]}")
        config["agents"]["defaults"].pop("pdfMaxBytesMb", None)
        current = json.loads(json.dumps(config))
        chief = current["agents"]["entries"]["chef-operations"]
        if backend == "ollama-vulkan":
            for retired in ("redacteur-technique", "ingenieur-release-forges"):
                entry = json.loads(json.dumps(chief))
                entry["default"] = False
                current["agents"]["entries"][retired] = entry
        else:
            current["agents"]["entries"] = {"main": chief}
        preserved = state / "retired-workspace" / "history.md"
        preserved.parent.mkdir()
        preserved.write_text("historical user data")
        path.write_text(json.dumps(current))
        migration = state / "migration.json"
        migration.write_text(json.dumps(prepare_migration_patch(config, backend)))
        for dry_run in (True, False):
            command = [cli, "config", "patch", "--file", str(migration)]
            if dry_run:
                command.append("--dry-run")
            result = subprocess.run(
                command, env=env, capture_output=True, text=True, timeout=120, check=False
            )
            if result.returncode != 0:
                raise SystemExit(
                    f"Native roster migration rejected: {result.stderr[-2000:]} "
                    f"{result.stdout[-2000:]}"
                )
        result = subprocess.run(
            ["node", str(repo / "scripts/linux/retire_managed_agents.mjs"), cli],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            raise SystemExit(f"Native SDK retirement failed: {result.stderr[-4000:]}")
        result = subprocess.run(
            [cli, "config", "get", "agents", "--json"],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        roster = json.loads(result.stdout)
        if preserved.read_text() != "historical user data":
            raise SystemExit("Native migration altered workspace history")
        if set(roster.get("entries", {})) != set(config["agents"]["entries"]):
            raise SystemExit("Native migration did not converge to the six requested agents")
    print(
        f"NATIVE_SCHEMA=PASS backend={backend} retired_pdf_key=rejected migration=PASS version={pin}"
    )
