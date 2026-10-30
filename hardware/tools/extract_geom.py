"""Extrai centros de conectores (em unidades do viewBox) de SVGs de partes do Fritzing.

Usa o Chromium (Playwright) para resolver transformações aninhadas com precisão.
Uso: python extract_geom.py <svg> <regex_id> > saida.json
"""
import json, re, sys
from playwright.sync_api import sync_playwright

JS = """
([pattern]) => {
  const svg = document.querySelector('svg');
  const vb = svg.viewBox.baseVal;
  const W = vb.width || parseFloat(svg.getAttribute('width'));
  const H = vb.height || parseFloat(svg.getAttribute('height'));
  svg.setAttribute('width', W); svg.setAttribute('height', H);
  const root = svg.getBoundingClientRect();
  const re = new RegExp(pattern);
  const out = {};
  svg.querySelectorAll('[id]').forEach(el => {
    if (!re.test(el.id)) return;
    const r = el.getBoundingClientRect();
    out[el.id] = {cx: r.left - root.left + r.width/2 + vb.x, cy: r.top - root.top + r.height/2 + vb.y, w: r.width, h: r.height};
  });
  const attrs = {width: svg.getAttribute('width'), height: svg.getAttribute('height'),
                 viewBox: [vb.x, vb.y, vb.width, vb.height]};
  return {attrs, pins: out};
}
"""

def main(path, pattern):
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 4000, "height": 3000})
        pg.goto("file://" + path)
        res = pg.evaluate(JS, [pattern])
        b.close()
    print(json.dumps(res, indent=1))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
