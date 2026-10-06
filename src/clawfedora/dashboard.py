"""Small loopback dashboard. Reading it never starts a model or a worker."""

from __future__ import annotations

import json
import socket
import threading
from contextlib import suppress
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit
from urllib.request import urlopen

from clawfedora import project_ui
from clawfedora.core_config import root_contract
from clawfedora.knowledge import build_index, search, store_note
from clawfedora.learning import awaiting, pending_feedback, submit
from clawfedora.local_http import LocalServer
from clawfedora.mentor import profile, save_profile
from clawfedora.project_common import read_json
from clawfedora.project_control import is_paused, progress, request_pause, worker_active
from clawfedora.project_engine import current_status, transition_project
from clawfedora.project_revision import impact, revise
from clawfedora.project_worker import review_project, run_project_tasks, worker_lock


def snapshot(repo_root: Path, runtime: Path) -> dict[str, Any]:
    projects: list[dict[str, Any]] = []
    for path in sorted((runtime / "projects").glob("*/project.json"))[:100]:
        if path.is_symlink() or path.parent.is_symlink():
            continue
        try:
            manifest = read_json(path)
            # The path is contract-owned, not inferred from dashboard labels.
            from clawfedora.core_config import core_contract

            task_relative = core_contract(repo_root, "orchestration_policy.yaml")["artifacts"][
                "assignments"
            ]
            tasks_file = path.parent / task_relative
            tasks = read_json(tasks_file).get("tasks", []) if tasks_file.is_file() else []
            projects.append(
                {
                    "project_id": manifest["project_id"],
                    "title": manifest["title"],
                    "status": manifest["status"],
                    "paused": is_paused(runtime, path.parent),
                    "tasks": tasks,
                    "completed": sum(t.get("status") == "PASS" for t in tasks),
                    "total": len(tasks),
                    "awaiting_practice": bool(awaiting(path.parent)),
                    "awaiting_feedback": bool(pending_feedback(path.parent)),
                }
            )
        except (OSError, ValueError, KeyError):
            continue
    memory: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            if key in {"MemTotal", "MemAvailable"}:
                memory[key] = int(value.strip().split()[0]) * 1024
    except (OSError, ValueError):
        pass
    models: list[dict[str, Any]] = []
    ollama_available = False
    try:
        with urlopen("http://127.0.0.1:11434/api/ps", timeout=2) as response:
            raw = response.read(64001)
        if len(raw) > 64000:
            raise ValueError("inventaire trop volumineux")
        inventory = json.loads(raw)
        models = [
            {"name": str(m.get("name", "")), "size_vram": int(m.get("size_vram", 0))}
            for m in inventory.get("models", [])[:4]
        ]
        ollama_available = True
    except (OSError, ValueError, TypeError):
        pass
    try:
        with socket.create_connection(("127.0.0.1", 18789), timeout=0.3):
            gateway_available = True
    except OSError:
        gateway_available = False
    versions = root_contract(repo_root, "runtime_versions.yaml")
    return {
        "profile": "gaming" if (runtime / "state/gaming-mode").exists() else "daily",
        "memory": memory,
        "models": models,
        "ollama_available": ollama_available,
        "gateway_available": gateway_available,
        "worker": progress(runtime),
        "projects": projects,
        "mentor": profile(runtime),
        "webui_installed": (runtime / "state/webui/enabled").is_file(),
        "versions": {
            "openclaw": versions["openclaw"]["version"],
            "ollama": versions["ollama"]["version"],
        },
    }


class DashboardServer(LocalServer):
    repo_root: Path
    runtime: Path
    errors: dict[str, str]


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardServer

    def _project(self, project_id: str) -> Path:
        # Select a path found on disk; request values never form filesystem paths.
        root = self.server.runtime / "projects"
        if root.is_symlink():
            raise ValueError("racine de projets liée interdite")
        for manifest in root.glob("*/project.json"):
            project = manifest.parent
            if project.name != project_id:
                continue
            if project.is_symlink() or manifest.is_symlink():
                raise ValueError("projet lié interdit")
            if project.resolve().parent != root.resolve():
                raise ValueError("projet hors runtime")
            return project
        raise ValueError("projet existant requis")

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _origin(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def _valid_host(self) -> bool:
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def _send(
        self,
        status: int,
        value: Any,
        content_type: str = "application/json",
        *,
        attachment: str = "",
    ) -> None:
        body = (
            json.dumps(value, ensure_ascii=False).encode()
            if content_type == "application/json"
            else value
        )
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if attachment:
            self.send_header(
                "Content-Disposition", "attachment; filename*=UTF-8''" + quote(attachment, safe="")
            )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self._valid_host():
            self._send(403, {"error": "hôte local requis"})
            return
        url = urlsplit(self.path)
        try:
            if url.path in {"/", "/dashboard.js", "/dashboard.css"}:
                name = {
                    "/": "dashboard.html",
                    "/dashboard.js": "dashboard.js",
                    "/dashboard.css": "dashboard.css",
                }[url.path]
                kind = {
                    "dashboard.html": "text/html",
                    "dashboard.js": "text/javascript",
                    "dashboard.css": "text/css",
                }[name]
                self._send(200, (Path(__file__).parent / "web" / name).read_bytes(), kind)
            elif url.path == "/api/status":
                value = snapshot(self.server.repo_root, self.server.runtime)
                value["errors"] = dict(self.server.errors)
                self._send(200, value)
            elif url.path in {"/api/project", "/api/artifact"}:
                query = parse_qs(url.query)
                project = self._project(query["project"][0])
                if url.path == "/api/project":
                    self._send(200, project_ui.details(project))
                else:
                    self._artifact(project, query.get("path", [""])[0])
            elif url.path == "/api/search":
                query = parse_qs(url.query)
                project = self._project(query["project"][0])
                self._send(200, search(self.server.repo_root, project, query.get("q", [""])[0]))
            else:
                self._send(404, {"error": "page absente"})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self._send(400, {"error": str(exc)})

    def do_POST(self) -> None:
        if not self._valid_host() or self.headers.get("Origin") != self._origin():
            self._send(403, {"error": "origine locale requise"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            limit = (
                11_000_000
                if self.path == "/api/create"
                else 150000
                if self.path == "/api/practice"
                else 40000
            )
            if (
                self.headers.get("Content-Type") != "application/json"
                or not 0 < length <= limit
                or self.headers.get("Transfer-Encoding")
            ):
                raise ValueError("requête JSON bornée requise")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("objet JSON requis")
            if self.path == "/api/create":
                project = project_ui.create_from_browser(
                    self.server.repo_root, self.server.runtime, data
                )
                self._send(201, {"project_id": project.name})
                return
            if self.path == "/api/mentor":
                with worker_lock(self.server.runtime, allow_gaming=True):
                    value = save_profile(self.server.runtime, data)
                self._send(200, value)
                return
            project = self._project(str(data["project_id"]))
            if self.path in {"/api/propose-analysis", "/api/propose-plan", "/api/audit"}:
                if worker_active(self.server.runtime):
                    raise ValueError("Une tâche ou discussion est active; attendre sa fin.")
                kind = (
                    str(data.get("kind", ""))
                    if self.path == "/api/audit"
                    else self.path.removeprefix("/api/propose-")
                )
                if self.path == "/api/audit" and kind not in {"validation", "review"}:
                    raise ValueError("audit validation ou review requis")
                if (self.server.runtime / "state/gaming-mode").exists():
                    raise ValueError("Reprendre le profil quotidien avant une génération.")
                self.server.errors.pop(project.name, None)
                threading.Thread(target=self._prepare, args=(project, kind), daemon=False).start()
            elif self.path == "/api/approve":
                if data.get("human_approved") is not True or not isinstance(
                    data.get("proposal"), dict
                ):
                    raise ValueError("approbation humaine explicite et proposition requises")
                project_ui.approve(
                    self.server.repo_root,
                    self.server.runtime,
                    project,
                    str(data["kind"]),
                    data["proposal"],
                )
            elif self.path == "/api/clarify":
                project_ui.clarify(
                    self.server.repo_root,
                    self.server.runtime,
                    project,
                    str(data["id"]),
                    str(data["answer"]),
                )
            elif self.path == "/api/complete":
                if data.get("human_approved") is not True:
                    raise ValueError("approbation finale humaine requise")
                project_ui.complete(self.server.repo_root, self.server.runtime, project)
            elif self.path == "/api/practice":
                submit(
                    self.server.repo_root, self.server.runtime, project, str(data["task_id"]), data
                )
            elif self.path == "/api/revision-impact":
                self._send(200, {"affected_tasks": impact(project, str(data["task_id"]))})
                return
            elif self.path == "/api/revise":
                with worker_lock(self.server.runtime, allow_gaming=True):
                    self._send(
                        200,
                        revise(
                            project,
                            str(data["task_id"]),
                            str(data["reason"]),
                            human_approved=data.get("human_approved") is True,
                        ),
                    )
                return
            elif self.path == "/api/pause":
                request_pause(self.server.runtime, project)
            elif self.path == "/api/resume":
                if worker_active(self.server.runtime):
                    raise ValueError("Une tâche est encore active. Attendre sa fin.")
                if current_status(project) not in {"ASSIGNED", "IN_PROGRESS"}:
                    raise ValueError("Un plan doit être assigné avant l'exécution.")
                if (self.server.runtime / "state/gaming-mode").exists():
                    raise ValueError("Reprendre le profil quotidien avant l'exécution.")
                self.server.errors.pop(project.name, None)
                threading.Thread(target=self._run, args=(project,), daemon=False).start()
            elif self.path in {"/api/index", "/api/remember"}:
                with worker_lock(self.server.runtime, allow_gaming=True):
                    if self.path == "/api/remember":
                        store_note(
                            self.server.repo_root, project, str(data["title"]), str(data["text"])
                        )
                    report = build_index(self.server.repo_root, project)
                self._send(200, report)
                return
            else:
                self._send(404, {"error": "action absente"})
                return
            self._send(202, {"accepted": True})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self._send(400, {"error": str(exc)})

    def _artifact(self, project: Path, relative: str) -> None:
        from clawfedora.project_common import assert_no_symlinks

        assert_no_symlinks(project, label="livrable")
        for scope in ("intake", "deliverables", "diagrams", "evidence"):
            for path in (project / scope).rglob("*"):
                if path.is_file() and path.relative_to(project).as_posix() == relative:
                    if path.stat().st_size > 8_000_000:
                        raise ValueError("fichier trop volumineux pour le téléchargement web")
                    self._send(
                        200, path.read_bytes(), "application/octet-stream", attachment=path.name
                    )
                    return
        raise ValueError("fichier absent du projet")

    def _prepare(self, project: Path, kind: str) -> None:
        try:
            if kind in {"analysis", "plan"}:
                project_ui.propose(self.server.repo_root, self.server.runtime, project, kind)
            else:
                path = review_project(self.server.repo_root, self.server.runtime, project, kind)
                if read_json(path)["verdict"] != "PASS":
                    raise ValueError("Audit FAIL: consulter les constats avant reprise.")
                with worker_lock(self.server.runtime):
                    transition_project(
                        self.server.repo_root,
                        project,
                        "REVIEW" if kind == "validation" else "PACKAGING",
                        actor="auditeur-qualite",
                        reason="web_audit_passed",
                    )
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            self.server.errors[project.name] = str(exc)

    def _run(self, project: Path) -> None:
        try:
            results = run_project_tasks(
                self.server.repo_root, self.server.runtime, project, resume=True
            )
            failures = [r["summary"] for r in results if r["status"] == "FAIL"]
            if failures:
                self.server.errors[project.name] = str(failures[0])
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            self.server.errors[project.name] = str(exc)


def make_server(repo_root: Path, runtime: Path, port: int = 18890) -> DashboardServer:
    server = DashboardServer(("127.0.0.1", port), DashboardHandler)
    server.repo_root, server.runtime, server.errors = repo_root, runtime, {}
    return server


def serve(repo_root: Path, runtime: Path, port: int = 18890) -> None:
    with make_server(repo_root, runtime, port) as server:
        print(f"Tableau de bord : http://127.0.0.1:{server.server_port}", flush=True)
        with suppress(KeyboardInterrupt):
            server.serve_forever()
