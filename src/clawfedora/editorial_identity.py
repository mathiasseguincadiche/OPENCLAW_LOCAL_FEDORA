"""Offline editorial artwork from a bounded, reusable specification."""
from __future__ import annotations

import json
import re
from html import escape
from typing import Any

IDENTITY_ROLES = frozenset({"architecte-solutions", "redacteur-pedagogique"})
VARIANTS = {
    "cover": (1500, 600), "hero": (1440, 420), "section": (1200, 280),
    "exercise": (1200, 320), "logo": (256, 256),
}
PALETTES = {
    "ocean": ("#10243A", "#175A78", "#64D8EA"),
    "forest": ("#102D29", "#1D6656", "#72E2AF"),
    "ember": ("#33201F", "#864631", "#FFC07B"),
    "indigo": ("#22213F", "#514A87", "#C2B5FF"),
    "graphite": ("#202A34", "#425D75", "#A2DAFF"),
}
MOTIFS = {
    "network": '<path d="M70 100L190 45 320 100 190 190Z M70 100L190 190 M190 45V190"/>'
    '<circle cx="70" cy="100" r="28"/><circle cx="190" cy="45" r="28"/>'
    '<circle cx="320" cy="100" r="28"/><circle cx="190" cy="190" r="28"/>',
    "pipeline": '<rect x="28" y="70" width="84" height="100" rx="14"/>'
    '<rect x="148" y="70" width="84" height="100" rx="14"/>'
    '<rect x="268" y="70" width="84" height="100" rx="14"/>'
    '<path d="M112 120H148M232 120H268 M60 120l10 10 15-22 '
    'M180 120l10 10 15-22 M300 120l10 10 15-22"/>',
    "observability": '<rect x="30" y="45" width="320" height="165" rx="18"/>'
    '<path d="M55 170L105 130 145 150 190 80 240 135 285 100 325 125"/>'
    '<path d="M55 80H325M55 125H325M55 175H325" opacity=".2"/>',
    "platform": '<path d="M190 30L350 105 190 180 30 105Z M30 145L190 220 350 145"/>'
    '<path d="M120 105L190 72 260 105 190 138Z"/>',
    "storage": '<ellipse cx="190" cy="60" rx="120" ry="35"/>'
    '<path d="M70 60V175C70 222 310 222 310 175V60 M70 118C70 165 310 165 310 118"/>',
}


def _label(value: object, limit: int) -> str:
    if (
        not isinstance(value, str) or not 1 <= len(value.strip()) <= limit
        or value != value.strip() or not value.isprintable()
    ):
        raise ValueError("libellé éditorial vide, trop long ou invalide")
    return value


def _luminance(color: str) -> float:
    raw = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    channels = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in raw]
    return sum(v * w for v, w in zip(channels, (.2126, .7152, .0722), strict=True))


def _contrast(left: str, right: str) -> float:
    high, low = sorted((_luminance(left), _luminance(right)), reverse=True)
    return (high + .05) / (low + .05)


def render(spec: object) -> tuple[dict[str, Any], str]:
    if not isinstance(spec, dict) or set(spec) != {
        "project", "tagline", "variant", "motif", "palette", "section",
    }:
        raise ValueError("identité : six champs exacts requis")
    project, tagline = _label(spec["project"], 26), _label(spec["tagline"], 60)
    section = _label(spec["section"], 30)
    variant, motif, palette = spec["variant"], spec["motif"], spec["palette"]
    if not isinstance(variant, str) or variant not in VARIANTS:
        raise ValueError("variante graphique inconnue")
    if not isinstance(motif, str) or motif not in MOTIFS:
        raise ValueError("motif graphique inconnu")
    colors: tuple[str, ...]
    if isinstance(palette, str) and palette in PALETTES:
        colors = PALETTES[palette]
    elif isinstance(palette, list) and len(palette) == 3 and all(
        isinstance(c, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", c) for c in palette
    ):
        colors = tuple(c.upper() for c in palette)
    else:
        raise ValueError("palette nommée ou trois couleurs HEX requises")
    bg, secondary, accent = colors
    if (
        _contrast("#FFFFFF", bg) < 7 or _contrast("#FFFFFF", secondary) < 4.5
        or _contrast(accent, bg) < 4.5
    ):
        raise ValueError("contraste insuffisant pour l'identité")
    width, height = VARIANTS[variant]
    artwork = (
        f'<g fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round" '
        f'stroke-linejoin="round">{MOTIFS[motif]}</g>'
    )
    if variant == "cover":
        body = (
            '<g transform="translate(500 140) scale(1.3)">'
            + artwork + '</g>'
            '<circle cx="750" cy="300" r="245" fill="none" stroke="#FFFFFF" opacity=".09"/>'
        )
    elif variant == "logo":
        body = (
            f'<rect x="24" y="24" width="208" height="208" rx="44" fill="{secondary}"/>'
            f'<g transform="translate(19 65) scale(.57)">{artwork}</g>'
        )
    else:
        headline = project if variant == "hero" else section
        line = tagline if variant == "hero" else project
        size = min(72 if variant == "hero" else 54, int(720 / len(headline)))
        subsize = min(22, int(680 / len(line)))
        body = (
            f'<rect x="48" y="52" width="7" height="{height - 104}" rx="3" fill="{accent}"/>'
            f'<text x="76" y="89" fill="#FFFFFF" font-size="19" font-weight="700">'
            'PROJET · INGÉNIERIE</text>'
            f'<text x="74" y="{height // 2 + 12}" fill="#FFFFFF" font-size="{size}" '
            f'font-weight="700">{escape(headline)}</text>'
            f'<text x="76" y="{height // 2 + 56}" fill="#FFFFFF" font-size="{subsize}">'
            f'{escape(line)}</text>'
            f'<g transform="translate({width - 445} {height // 2 - 115})">{artwork}</g>'
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">'
        f'<title id="title">{escape(project)} — {escape(section)}</title>'
        '<desc id="desc">Illustration éditoriale, pas une preuve technique.</desc>'
        '<defs><linearGradient id="surface" x1="0" y1="0" x2="1" y2="1">'
        f'<stop stop-color="{bg}"/><stop offset="1" stop-color="{secondary}"/>'
        '</linearGradient><pattern id="grid" width="48" height="48" patternUnits="userSpaceOnUse">'
        '<path d="M48 0H0V48" fill="none" stroke="#FFFFFF" stroke-opacity=".07"/>'
        '</pattern></defs>'
        f'<rect width="{width}" height="{height}" fill="url(#surface)"/>'
        f'<rect width="{width}" height="{height}" fill="url(#grid)"/>'
        f'<g font-family="DejaVu Sans,Arial,sans-serif">{body}</g></svg>\n'
    )
    return {
        "project": project, "tagline": tagline, "section": section,
        "variant": variant, "motif": motif, "palette": list(colors),
    }, svg


def from_json(content: str) -> tuple[str, str]:
    data, svg = render(json.loads(content))
    return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n", svg
