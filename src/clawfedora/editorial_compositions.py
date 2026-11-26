"""Bounded editorial art direction: distinct visual compositions, no raw markup input."""
from __future__ import annotations

from html import escape
from typing import Any

COMPOSITIONS = ("split", "editorial", "orbit", "blueprint")


def compose(data: dict[str, Any], width: int, height: int, artwork: str) -> str:
    """Render a non-legacy composition. Input has already passed identity validation."""
    variant, layout = data["variant"], data["composition"]
    bg, secondary, accent = data["palette"]
    project, section, tagline = (escape(data[k]) for k in ("project", "section", "tagline"))
    headline = project if variant == "hero" else section
    caption = tagline if variant == "hero" else project
    # All layouts keep visual content away from the outside of a cropped cover.
    if variant == "logo":
        if layout == "orbit":
            frame = f'<circle cx="128" cy="128" r="104" fill="{secondary}"/>'
        elif layout == "blueprint":
            frame = (
                f'<rect x="22" y="22" width="212" height="212" rx="12" fill="{secondary}"/>'
                f'<path d="M36 70V36H70M186 36H220V70M36 186V220H70M186 220H220V186" '
                f'fill="none" stroke="{accent}" stroke-width="3"/>'
            )
        else:
            frame = f'<rect x="24" y="24" width="208" height="208" rx="44" fill="{secondary}"/>'
        return frame + f'<g transform="translate(26 68) scale(.54)">{artwork}</g>'
    if variant == "cover":
        center = width // 2
        if layout == "orbit":
            geometry = "".join(
                f'<ellipse cx="{center}" cy="300" rx="{r}" ry="{r // 2}" '
                f'fill="none" stroke="{accent}" opacity=".25"/>' for r in (180, 300, 480)
            )
        elif layout == "blueprint":
            geometry = (
                f'<rect x="420" y="118" width="660" height="364" rx="18" '
                f'fill="{bg}" stroke="{accent}" stroke-opacity=".45"/>'
                f'<path d="M350 300H1150M750 80V520" stroke="{accent}" opacity=".2"/>'
            )
        else:
            geometry = (
                f'<path d="M0 420L1500 100V600H0Z" fill="{secondary}" opacity=".65"/>'
                f'<rect x="480" y="110" width="540" height="380" rx="42" '
                f'fill="{bg}" stroke="{accent}" stroke-opacity=".38"/>'
            )
        return geometry + f'<g transform="translate(503 144) scale(1.3)">{artwork}</g>'
    # Each composition has its own visual hierarchy; no text or geometry supplied as SVG.
    if layout == "editorial":
        return (
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="{bg}"/>'
            f'<rect x="0" y="0" width="12" height="{height}" fill="{accent}"/>'
            f'<rect x="{width - 440}" y="24" width="410" height="{height - 48}" '
            f'rx="20" fill="{secondary}"/>'
            f'<g transform="translate({width - 425} {height // 2 - 115})">{artwork}</g>'
            + _copy(headline, caption, section, 52, height, width - 530)
        )
    if layout == "orbit":
        cx, cy = width - 285, height // 2
        rings = "".join(
            f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" '
            f'stroke="{accent}" stroke-opacity=".24"/>' for radius in (65, 108, 135)
        )
        return (
            rings + f'<g transform="translate({cx - 152} {cy - 92}) scale(.8)">{artwork}</g>'
            + _copy(headline, caption, section, 52, height, width - 480)
        )
    if layout == "blueprint":
        return (
            f'<rect x="26" y="22" width="{width - 52}" height="{height - 44}" rx="8" '
            f'fill="none" stroke="{accent}" stroke-opacity=".48"/>'
            f'<path d="M{width - 465} 42V{height - 42}" stroke="{accent}" opacity=".5"/>'
            f'<g transform="translate({width - 435} {height // 2 - 115})">{artwork}</g>'
            + _copy(headline, caption, section, 52, height, width - 540)
        )
    raise ValueError("composition non reconnue")


def _copy(headline: str, caption: str, section: str, x: int,
          height: int, available: int) -> str:
    # Conservative width estimate using raw escaped length, never an unbounded font size.
    title_size = min(58, available // max(1, len(headline)))
    caption_size = min(23, available // max(1, len(caption)))
    label_size = min(16, available // max(1, len(section)))
    return (
        f'<text x="{x}" y="62" fill="#FFFFFF" opacity=".86" font-size="{label_size}" '
        f'font-weight="600">{section}</text>'
        f'<text x="{x}" y="{height // 2 + 7}" fill="#FFFFFF" font-size="{title_size}" '
        f'font-weight="700">{headline}</text>'
        f'<text x="{x}" y="{height // 2 + 49}" fill="#FFFFFF" font-size="{caption_size}">'
        f'{caption}</text>'
    )
