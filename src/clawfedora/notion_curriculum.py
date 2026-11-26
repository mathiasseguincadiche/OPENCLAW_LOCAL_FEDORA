"""Bounded relational curriculum for a newly created studio, never an existing wiki."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from clawfedora import notion_editorial as ne
from clawfedora import notion_write as nw

Request = Callable[..., dict[str, Any]]
ACTIVITY_FIELDS: dict[str, dict[str, Any]] = {
    "Activité": {"title": {}}, "Ordre": {"number": {"format": "number"}},
    "Validé": {"checkbox": {}}, "Objectif": {"rich_text": {}},
}
MODULE_FIELDS: dict[str, dict[str, Any]] = {
    "Module": {"title": {}}, "Ordre": {"number": {"format": "number"}},
    "Objectif": {"rich_text": {}},
}


def validate(value: object, titles: set[str]) -> list[str]:
    if not isinstance(value, dict) or set(value) != {"modules"}:
        raise nw.NotionWriteError("parcours relationnel : modules requis")
    modules = value["modules"]
    if not isinstance(modules, list) or not 1 <= len(modules) <= 5:
        raise nw.NotionWriteError("un à cinq modules")
    if titles & {"Modules du parcours", "Activités du parcours"}:
        raise nw.NotionWriteError("titre de base réservé")
    names: set[str] = set()
    activity_names: set[str] = set()
    files: list[str] = []
    for module in modules:
        if (
            not isinstance(module, dict)
            or not {"title", "objective", "activities", "page"} <= set(module)
            or not set(module) <= {"title", "objective", "activities", "page", "cover_file"}
        ):
            raise nw.NotionWriteError("module mal formé")
        name = nw._text(module["title"])
        nw._text(module["objective"])
        if name in names or not isinstance(module["page"], str) or module["page"] not in titles:
            raise nw.NotionWriteError("module dupliqué ou page inconnue")
        names.add(name)
        if "cover_file" in module:
            if not isinstance(module["cover_file"], str):
                raise nw.NotionWriteError("couverture locale invalide")
            files.append(module["cover_file"])
        activities = module["activities"]
        if not isinstance(activities, list) or not 1 <= len(activities) <= 4:
            raise nw.NotionWriteError("une à quatre activités par module")
        for activity in activities:
            if not isinstance(activity, dict) or set(activity) != {"title", "objective"}:
                raise nw.NotionWriteError("activité mal formée")
            title = nw._text(activity["title"])
            nw._text(activity["objective"])
            if title in activity_names:
                raise nw.NotionWriteError("activité dupliquée")
            activity_names.add(title)
    if len(activity_names) > 12:
        raise nw.NotionWriteError("douze activités maximum")
    return files


def _id(value: object) -> str:
    return nw._id(str(value))


def _database(request: Request, parent: str, title: str,
              fields: dict[str, dict[str, Any]]) -> tuple[str, str, dict[str, Any]]:
    definition = {
        "parent": {"type": "page_id", "page_id": parent},
        "title": ne._rich(title), "is_inline": True,
        "initial_data_source": {"properties": fields},
    }
    db = _id(request("POST", "/v1/databases", body=definition).get("id"))
    actual = request("GET", f"/v1/databases/{db}")
    if (
        _id(actual.get("id")) != db or actual.get("in_trash")
        or actual.get("parent", {}).get("type") != "page_id"
        or _id(actual.get("parent", {}).get("page_id")) != parent
        or not ne._matches(definition["title"], actual.get("title"))
        or not isinstance(actual.get("data_sources"), list) or len(actual["data_sources"]) != 1
    ):
        raise nw.NotionWriteError("base relationnelle non confirmée")
    source = _id(actual["data_sources"][0].get("id"))
    schema = _schema(request, source, fields)
    return db, source, schema


def _schema(request: Request, source: str,
            fields: dict[str, dict[str, Any]]) -> dict[str, Any]:
    actual = request("GET", f"/v1/data_sources/{source}")
    schema = actual.get("properties")
    if _id(actual.get("id")) != source or not isinstance(schema, dict):
        raise nw.NotionWriteError("source de données non confirmée")
    for name, definition in fields.items():
        kind = next(iter(definition))
        prop = schema.get(name, {})
        if prop.get("type") != kind:
            raise nw.NotionWriteError("type de propriété non confirmé")
        if kind == "relation" and (
            _id(prop.get(kind, {}).get("data_source_id")) != definition[kind]["data_source_id"]
            or prop.get(kind, {}).get("type") != "single_property"
        ):
            raise nw.NotionWriteError("cible de relation non confirmée")
        if kind == "rollup" and not ne._matches(definition[kind], prop.get(kind)):
            raise nw.NotionWriteError("agrégation non confirmée")
    return schema


def _row(request: Request, source: str, properties: dict[str, Any], *,
         cover: str | None = None, page: str | None = None) -> str:
    definition: dict[str, Any] = {
        "parent": {"type": "data_source_id", "data_source_id": source},
        "properties": properties,
    }
    if cover is not None:
        definition["cover"] = {"type": "file_upload", "file_upload": {"id": cover}}
    if page is not None:
        definition["children"] = [ne._block("link_to_page", {
            "type": "page_id", "page_id": page,
        })]
    ident = _id(request("POST", "/v1/pages", body=definition).get("id"))
    actual = request("GET", f"/v1/pages/{ident}")
    if (
        _id(actual.get("id")) != ident or actual.get("in_trash")
        or actual.get("parent", {}).get("type") != "data_source_id"
        or _id(actual.get("parent", {}).get("data_source_id")) != source
    ):
        raise nw.NotionWriteError("ligne de parcours non confirmée")
    observed = actual.get("properties", {})
    for name, expected in properties.items():
        prop = observed.get(name, {})
        if "relation" in expected:
            wanted = [_id(v["id"]) for v in expected["relation"]]
            found = [_id(v["id"]) for v in prop.get("relation", [])]
            if set(wanted) != set(found) or len(wanted) != len(found) or prop.get("has_more"):
                raise nw.NotionWriteError("liens d'activités non confirmés")
        elif not ne._matches(expected, prop):
            raise nw.NotionWriteError("propriété de ligne différente")
    if cover is not None:
        actual_cover = actual.get("cover") or {}
        if actual_cover.get("type") != "file" or not actual_cover.get("file", {}).get("url"):
            raise nw.NotionWriteError("couverture de carte non confirmée")
    if page is not None:
        reply = request("GET", f"/v1/blocks/{ident}/children?page_size=100")
        blocks = reply.get("results", [])
        if (
            reply.get("has_more") or len(blocks) != 1 or blocks[0].get("type") != "link_to_page"
            or blocks[0]["link_to_page"].get("type") != "page_id"
            or _id(blocks[0]["link_to_page"].get("page_id")) != page
        ):
            raise nw.NotionWriteError("navigation de carte non confirmée")
    return ident


def _view(request: Request, db: str, source: str, schema: dict[str, Any],
          name: str, kind: str, *, incomplete: bool = False) -> str:
    definition: dict[str, Any] = {
        "database_id": db, "data_source_id": source, "name": name, "type": kind,
        "sorts": [{"property": "Ordre", "direction": "ascending"}],
    }
    if kind == "gallery":
        definition["configuration"] = {
            "type": "gallery", "cover": {"type": "page_cover"}, "cover_size": "medium",
        }
        definition["position"] = {"type": "start"}
    if incomplete:
        definition["filter"] = {"property": "Validé", "checkbox": {"equals": False}}
    ident = _id(request("POST", "/v1/views", body=definition).get("id"))
    actual = request("GET", f"/v1/views/{ident}")
    if (
        _id(actual.get("id")) != ident or actual.get("type") != kind
        or actual.get("name") != name or _id(actual.get("parent", {}).get("database_id")) != db
    ):
        raise nw.NotionWriteError("vue avancée non confirmée")
    sorts = actual.get("sorts", [])
    if len(sorts) != 1 or sorts[0].get("direction") != "ascending" or (
        sorts[0].get("property") not in {"Ordre", schema["Ordre"].get("id")}
    ):
        raise nw.NotionWriteError("tri de la vue avancée non confirmé")
    if kind == "gallery" and not ne._matches(
        definition["configuration"], actual.get("configuration"),
    ):
        raise nw.NotionWriteError("configuration galerie non confirmée")
    if incomplete:
        observed = actual.get("filter", {})
        if (
            observed.get("property") not in {"Validé", schema["Validé"].get("id")}
            or observed.get("checkbox") != {"equals": False}
        ):
            raise nw.NotionWriteError("filtre des activités non confirmé")
    return ident


def create(request: Request, home: str, spec: dict[str, Any],
           pages: dict[str, str], uploads: dict[str, str]) -> dict[str, Any]:
    activity_db, activity_source, activity_schema = _database(
        request, home, "Activités du parcours", ACTIVITY_FIELDS,
    )
    fields = {**MODULE_FIELDS, "Activités": {"relation": {
        "data_source_id": activity_source, "type": "single_property", "single_property": {},
    }}}
    module_db, module_source, _ = _database(request, home, "Modules du parcours", fields)
    # PATCH only the source created above, after relation schema readback.
    rollup = {"rollup": {"relation_property_name": "Activités",
                         "rollup_property_name": "Validé", "function": "percent_checked"}}
    request("PATCH", f"/v1/data_sources/{module_source}", body={
        "properties": {"Progression": rollup},
    })
    schema = _schema(request, module_source, {**fields, "Progression": rollup})
    modules: list[dict[str, Any]] = []
    order = 0
    for index, module in enumerate(spec["modules"], 1):
        rows: list[str] = []
        for activity in module["activities"]:
            order += 1
            rows.append(_row(request, activity_source, {
                "Activité": {"title": ne._rich(activity["title"])},
                "Ordre": {"number": order}, "Validé": {"checkbox": False},
                "Objectif": {"rich_text": ne._rich(activity["objective"])},
            }))
        ident = _row(request, module_source, {
            "Module": {"title": ne._rich(module["title"])}, "Ordre": {"number": index},
            "Objectif": {"rich_text": ne._rich(module["objective"])},
            "Activités": {"relation": [{"id": row} for row in rows]},
        }, cover=uploads.get(module.get("cover_file", "")), page=pages[module["page"]])
        actual = request("GET", f"/v1/pages/{ident}")
        progress = actual.get("properties", {}).get("Progression", {}).get("rollup", {})
        if progress.get("type") != "number" or progress.get("number") != 0:
            raise nw.NotionWriteError("progression initiale non confirmée ; vérifier le rollup")
        modules.append({"page_id": ident, "activities": rows, "initial_progress": 0})
    gallery = _view(request, module_db, module_source, schema, "Explorer", "gallery")
    pending = _view(request, activity_db, activity_source, activity_schema,
                    "À réaliser", "table", incomplete=True)
    return {"activity_source": activity_source, "module_source": module_source,
            "activity_database": activity_db, "module_database": module_db,
            "modules": modules, "gallery_view": gallery, "pending_view": pending,
            "progression_scope": "Activités cochées manuellement, pas compétences certifiées"}
