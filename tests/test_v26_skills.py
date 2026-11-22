"""Contrat de déploiement V26 : simulations et refus avant mutation."""
import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "v26_deployer", ROOT / "scripts/linux/20_deploy_v26_skills.py"
)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_v26_catalog_and_dry_run():
    with tempfile.TemporaryDirectory() as tmp:
        runtime = Path(tmp)
        allocation = json.loads((ROOT / "config/v26_skills.json").read_text())
        assert len(allocation) == 7
        assert len({s for names in allocation.values() for s in names}) == 11
        for agent in allocation:
            root = runtime / "workspaces" / agent
            root.mkdir(parents=True)
            (root / ".openclaw-fedora-managed").write_text(json.dumps({
                "managed_by": "OPENCLAW_LOCAL_FEDORA", "agent_id": agent
            }))
        actions = module.plan(runtime)
        assert len(actions) == 28
        assert module.main(["--runtime-root", str(runtime)]) == 0
        assert not any((runtime / "workspaces" / a / "skills").exists() for a in allocation)


def test_v26_install_collision_and_unmanaged_refusal():
    with tempfile.TemporaryDirectory() as tmp:
        runtime = Path(tmp)
        allocation = json.loads((ROOT / "config/v26_skills.json").read_text())
        for agent in allocation:
            root = runtime / "workspaces" / agent
            root.mkdir(parents=True)
            (root / ".openclaw-fedora-managed").write_text(json.dumps({
                "managed_by": "OPENCLAW_LOCAL_FEDORA", "agent_id": agent
            }))
        assert module.main(["--runtime-root", str(runtime), "--apply"]) == 0
        assert module.main(["--runtime-root", str(runtime), "--apply"]) == 2
        assert all(
            {p.name for p in (runtime / "workspaces" / agent / "skills").iterdir()} == set(names)
            for agent, names in allocation.items()
        )
        for agent in allocation:
            for name in allocation[agent]:
                shutil_target = runtime / "workspaces" / agent / "skills" / name
                assert (shutil_target / "SKILL.md").is_file()
