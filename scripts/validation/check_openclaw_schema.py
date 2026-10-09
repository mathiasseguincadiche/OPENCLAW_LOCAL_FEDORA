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
with tempfile.TemporaryDirectory(prefix="clawfedora-native-schema-") as temporary:
    state = Path(temporary)
    toolkit = state / "runtime/extensions/clawfedora-toolkit"
    shutil.copytree(repo / "plugins/clawfedora-toolkit", toolkit)
    toolkit.chmod(0o750)
    for asset in toolkit.iterdir():
        asset.chmod(0o640)
    config = build_openclaw_patch(repo, state)
    config["plugins"] = {
        **config["plugins"],
        "allow": ["parallel", "memory-core", "clawfedora-toolkit"],
        "load": {"paths": [str(plugin), str(toolkit)]},
        "entries": {**config["plugins"]["entries"], "parallel": {"enabled": True}},
    }
    path = state / "openclaw.json"
    env = dict(
        os.environ,
        OPENCLAW_STATE_DIR=str(state),
        OPENCLAW_CONFIG_PATH=str(path),
        OLLAMA_API_KEY="ollama-local",
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
                raise SystemExit(f"Native schema rejected the configuration: {payload}")
            blocked = [
                item
                for item in payload.get("warnings", [])
                if "blocked" in str(item).lower() or "not available" in str(item).lower()
            ]
            if blocked:
                raise SystemExit(f"Plugin validation incomplete: {blocked[:2]}")
    config["agents"]["defaults"].pop("pdfMaxBytesMb", None)
    # The cloud provider (loopback gateway) must also be accepted by the real schema.
    cloud_config = build_openclaw_patch(repo, state, cloud_enabled=True)
    cloud_config["plugins"] = config["plugins"]
    path.write_text(json.dumps(cloud_config))
    result = subprocess.run(
        [cli, "config", "validate", "--json"],
        env=dict(env, CLAWFEDORA_CLOUD_GATEWAY_TOKEN="local-token"),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    try:
        payload = json.loads(result.stdout)
    except ValueError as exc:
        raise SystemExit(f"Native schema returned no JSON: {result.stderr[-1000:]}") from exc
    if result.returncode != 0 or payload.get("valid") is not True:
        raise SystemExit(f"Native schema rejected the cloud configuration: {payload}")
    if "cloudgw" not in cloud_config["models"]["providers"] or "cloudgw" in config["models"][
        "providers"
    ]:
        raise SystemExit("Cloud provider must exist only when the cloud is enabled")
    current = json.loads(json.dumps(config))
    # An installation that had the cloud on must lose its provider when it is switched off.
    current["models"]["providers"]["cloudgw"] = cloud_config["models"]["providers"]["cloudgw"]
    chief = current["agents"]["entries"]["chef-operations"]
    # An older installation still lists retired roles: the migration must remove them.
    for retired in ("redacteur-technique", "ingenieur-release-forges", "main"):
        entry = json.loads(json.dumps(chief))
        entry["default"] = False
        current["agents"]["entries"][retired] = entry
    preserved = state / "retired-workspace" / "history.md"
    preserved.parent.mkdir()
    preserved.write_text("historical user data")
    path.write_text(json.dumps(current))
    migration = state / "migration.json"
    migration.write_text(json.dumps(prepare_migration_patch(config)))
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
    providers = subprocess.run(
        [cli, "config", "get", "models.providers", "--json"],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    if "cloudgw" in json.loads(providers.stdout):
        raise SystemExit("Native migration kept the cloud provider after the cloud was disabled")
    if preserved.read_text() != "historical user data":
        raise SystemExit("Native migration altered workspace history")
    if set(roster.get("entries", {})) != set(config["agents"]["entries"]):
        raise SystemExit("Native migration did not converge to the seven requested agents")
print(
    f"NATIVE_SCHEMA=PASS retired_pdf_key=rejected migration=PASS version={pin}"
)
