"""Invoke the managed helpers through the pinned native OpenClaw plugin registry."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from clawfedora.agents import deploy_workspaces
from clawfedora.core_config import root_contract
from clawfedora.openclaw_config import build_openclaw_patch

repo = Path(__file__).resolve().parents[2]
cli = shutil.which("openclaw")
if not cli:
    raise SystemExit("Pinned OpenClaw CLI required")
package = Path(cli).resolve().parent
expected = str(root_contract(repo, "runtime_versions.yaml")["openclaw"]["version"])
if json.loads((package / "package.json").read_text())["version"] != expected:
    raise SystemExit("OpenClaw package version differs from the contract")
with tempfile.TemporaryDirectory(prefix="clawfedora-native-tools-") as temporary:
    runtime = Path(temporary)
    deploy_workspaces(repo, runtime)
    toolkit = runtime / "runtime/extensions/clawfedora-toolkit"
    shutil.copytree(repo / "plugins/clawfedora-toolkit", toolkit)
    toolkit.chmod(0o750)
    for asset in toolkit.iterdir():
        asset.chmod(0o640)
    (runtime / "runtime/venv").symlink_to(Path(sys.prefix))
    config = build_openclaw_patch(repo, runtime)
    config["plugins"]["allow"] = ["clawfedora-toolkit"]
    script = runtime / "check.mjs"
    script.write_text(
        "import {loadOpenClawPlugins} from "
        + json.dumps((package / "dist/plugins/loader.js").as_uri())
        + ";\nconst config="
        + json.dumps(config)
        + ";\nconst runtime="
        + json.dumps(str(runtime))
        + ";\n"
        + """
const registry=await loadOpenClawPlugins({config,onlyPluginIds:['clawfedora-toolkit'],
 activate:false,cache:false,throwOnLoadError:true});
if(registry.tools.length!==6) throw new Error('Native tool registration incomplete');
for (const [name,role,params] of [
 ['clawfedora_outline','ingenieur-devops',{kind:'runbook',title:'Sauvegarde'}],
 ['clawfedora_diagram','architecte-solutions',{nodes:['Atelier','Ollama'],edges:[[0,1]]}],
 ['clawfedora_check','auditeur-qualite',{format:'yaml',content:'server: 127.0.0.1'}],
 ['clawfedora_search','expert-recherche',{query:'OPS'}],
 ['clawfedora_lint','redacteur-pedagogique',{format:'markdown',content:'# Guide\\n\\nUne étape.\\n'}],
 ['clawfedora_tool_status','chef-operations',{}],
]) {
 const entry=registry.tools.find(x=>x.names.includes(name));
 const tool=entry.factory({agentId:role,workspaceDir:runtime+'/workspaces/'+role});
 if(!tool) throw new Error('Missing factory '+name);
 const result=await tool.execute('verification',params);
 if(!result.content?.[0]?.text) throw new Error('Missing result '+name);
 console.log('NATIVE_TOOL=PASS name='+name);
}
const entry=registry.tools.find(x=>x.names.includes('clawfedora_diagram'));
if(entry.factory({agentId:'chef-operations',workspaceDir:runtime+'/workspaces/chef-operations'})!==null)
 throw new Error('Role isolation failed');
console.log('NATIVE_ROLE_ISOLATION=PASS');
"""
    )
    result = subprocess.run(
        ["node", str(script)],
        env={
            **os.environ,
            "OPENCLAW_LOCAL_FEDORA_ROOT": str(runtime),
            "OPENCLAW_STATE_DIR": str(runtime / "state"),
        },
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise SystemExit(result.stderr[-3000:] + result.stdout[-3000:])
    print(result.stdout.strip())
