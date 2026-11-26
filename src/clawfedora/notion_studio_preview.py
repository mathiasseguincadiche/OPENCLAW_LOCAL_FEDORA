"""Offline, escaped studio preview. No scripts, network, or native-render claim."""
from __future__ import annotations

import base64
import os
from html import escape
from pathlib import Path
from typing import Any

from clawfedora import notion_write as nw

STYLE = """
:root{color-scheme:light dark;--bg:#fff;--ink:#253242;--line:#d4dce3;--soft:#eff4f8}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.65 system-ui,sans-serif}main{max-width:1000px;margin:auto;padding:24px}
article{margin:40px 0;border-top:1px solid var(--line);padding-top:24px}
h1,h2,h3{line-height:1.25}img{max-width:100%;height:auto;border-radius:8px}
.cover{width:100%;aspect-ratio:3/1;object-fit:cover}aside,pre,details{
background:var(--soft);border-radius:8px;padding:16px}pre{white-space:pre-wrap}
.columns{display:grid;grid-template-columns:1fr 1fr;gap:16px}
table{border-collapse:collapse;width:100%}td,th{border:1px solid var(--line);
padding:8px;text-align:left}nav{display:flex;flex-wrap:wrap;gap:16px}
a{color:inherit}figcaption{font-size:14px}figure{margin:16px 0}
@media(max-width:620px){main{padding:12px}.columns{grid-template-columns:1fr}}
@media(prefers-color-scheme:dark){:root{--bg:#131c25;--ink:#e4edf4;
--line:#3c4b59;--soft:#22303d}}
"""


def _text(block: dict[str, Any]) -> str:
    if "spans" not in block:
        return escape(str(block.get("text", "")))
    parts = []
    for span in block["spans"]:
        value = escape(span["text"])
        for flag, tag in (("bold", "strong"), ("italic", "em"), ("code", "code")):
            if span.get(flag):
                value = f"<{tag}>{value}</{tag}>"
        # Deliberately no live link: preview stays entirely offline.
        if "url" in span:
            value += " [lien]"
        parts.append(value)
    return "".join(parts)


def _blocks(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for block in blocks:
        kind = block["type"]
        text = _text(block)
        if kind.startswith("heading_"):
            level = int(kind[-1]) + 1
            parts.append(f"<h{level}>{text}</h{level}>")
        elif kind == "callout":
            parts.append(f"<aside>{escape(block['icon'])} {text}</aside>")
        elif kind == "code":
            parts.append(f"<pre><code>{text}</code></pre>")
        elif kind == "columns":
            cols = "".join(f"<div>{_blocks(c)}</div>" for c in block["columns"])
            parts.append(f'<div class="columns">{cols}</div>')
        elif kind == "toggle":
            parts.append(
                f"<details><summary>{text}</summary>{_blocks(block['children'])}</details>",
            )
        elif kind == "table":
            rows = []
            for index, row in enumerate(block["rows"]):
                tag = "th" if index == 0 else "td"
                cells = "".join(f"<{tag}>{escape(cell)}</{tag}>" for cell in row)
                rows.append(f"<tr>{cells}</tr>")
            parts.append("<table>" + "".join(rows) + "</table>")
        elif kind == "divider":
            parts.append("<hr>")
        elif kind == "table_of_contents":
            parts.append("<p>Sommaire natif prévu dans Notion.</p>")
        elif kind == "image":
            parts.append(f"<p>Image externe non chargée : {escape(block['caption'])}</p>")
        elif kind == "quote":
            parts.append(f"<blockquote>{text}</blockquote>")
        elif kind in {"bulleted_list_item", "numbered_list_item"}:
            parts.append(f"<p>• {text}</p>")
        else:
            parts.append(f"<p>{text}</p>")
    return "".join(parts)


def render(spec: dict[str, Any], records: list[dict[str, Any]],
           contents: dict[str, bytes], *, media_placeholders: bool = False) -> str:
    images = {
        row["name"]: "data:" + row["mime"] + ";base64,"
        + base64.b64encode(contents[row["name"]]).decode("ascii")
        for row in records
    }
    def source_image(name: str, alt: str, css: str = "") -> str:
        if name not in images and media_placeholders:
            return f"<p>Média privé à vérifier lors du plan : {escape(name)}</p>"
        src = images[name]
        return f'<img{css} src="{src}" alt="{escape(alt)}">'

    pages = [spec["home"], *spec["pages"]]
    navigation = "".join(
        f'<a href="#page-{i}">{escape(p["title"])}</a>' for i, p in enumerate(pages)
    )
    synced = ""
    if "navigation" in spec:
        synced = (f'<aside><strong>{escape(spec["navigation"]["title"])}</strong>'
                  f'<nav>{navigation}</nav><small>Navigation synchronisée prévue</small></aside>')
    sections = []
    for index, page in enumerate(pages):
        cover = ""
        if "cover_file" in page:
            cover = source_image(page["cover_file"], "Couverture locale", ' class="cover"')
        elif "cover" in page:
            cover = "<p>Couverture externe : non chargée dans cet aperçu.</p>"
        media = "".join(
            f'<figure>{source_image(item["file"], item["caption"])}'
            f'<figcaption>{escape(item["caption"])}</figcaption></figure>'
            for item in page.get("images", [])
        )
        title = escape(page["title"])
        sections.append(
            f'<article id="page-{index}">{cover}<h2>{title}</h2>'
            f'{_blocks(page["blocks"])}{media}{synced}</article>',
        )
    tracker = spec["tracker"]
    if tracker:
        rows = "".join(
            f"<tr><td>{i}</td><td>{escape(name)}</td><td>À réaliser</td></tr>"
            for i, name in enumerate(tracker["activities"], 1)
        )
        sections.append(
            f'<article><h2>{escape(tracker["title"])}</h2>'
            '<p>Simulation statique de la base et des vues, pas de progression réelle.</p>'
            '<table><tr><th>Ordre</th><th>Activité</th><th>État</th></tr>'
            f'{rows}</table></article>',
        )
    if "curriculum" in spec:
        cards = []
        page_indexes = {page["title"]: i for i, page in enumerate(pages)}
        for module in spec["curriculum"]["modules"]:
            cover = ""
            if "cover_file" in module:
                cover = source_image(module["cover_file"], "", ' class="cover"')
            items = "".join(
                f'<li>{escape(activity["title"])} — {escape(activity["objective"])}</li>'
                for activity in module["activities"]
            )
            target = page_indexes[module["page"]]
            cards.append(
                f'<aside>{cover}<h3>{escape(module["title"])}</h3>'
                f'<p>{escape(module["objective"])}</p><p>0 / {len(module["activities"])} '
                f'activités validées</p><a href="#page-{target}">Ouvrir le module</a>'
                f'<ul>{items}</ul></aside>',
            )
        sections.append('<article><h2>Parcours relationnel — simulation locale</h2>'
                        '<div class="columns">' + "".join(cards) + '</div></article>')
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "img-src data:; style-src 'unsafe-inline'\">"
        f'<title>Aperçu studio Notion</title><style>{STYLE}</style></head><body><main>'
        '<h1>Studio éditorial — aperçu privé</h1>'
        '<aside>Maquette locale, aucune publication. Ce n’est pas le rendu natif Notion. '
        'Ce fichier contient les images privées : ne pas partager.</aside>'
        f'<nav>{navigation}</nav>{"".join(sections)}</main></body></html>'
    )


def write(path: Path, content: str) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        raise nw.NotionWriteError("aperçu existant ou inaccessible") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
