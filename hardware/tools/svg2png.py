"""Converte SVG -> PNG de alta resolucao usando o Chromium do Playwright (apenas ferramenta de build)."""
from __future__ import annotations

import re
import sys
from pathlib import Path


def svg_to_png(svg_path: str | Path, png_path: str | Path, scale: float = 2.0) -> None:
    from playwright.sync_api import sync_playwright
    svg_text = Path(svg_path).read_text(encoding="utf-8")
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg_text)
    w, h = (float(m.group(1)), float(m.group(2))) if m else (1600.0, 900.0)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": int(w), "height": int(h)}, device_scale_factor=scale)
        pg.goto("file://" + str(Path(svg_path).resolve()))
        pg.screenshot(path=str(png_path), full_page=False, clip={"x": 0, "y": 0, "width": w, "height": h})
        b.close()


if __name__ == "__main__":
    svg_to_png(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 2.0)
