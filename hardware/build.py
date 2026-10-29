"""Orquestrador: netlist canonica -> diagramas, .fzz, Wokwi, tabelas e guia HTML (reprodutivel).

Uso:  python -m hardware.build [--out hardware/out] [--png]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from . import export_fz, export_wokwi, guide_html, model, reports
from .render_bb import Scene, render_scene
from .render_schematic import render_schematic

ROOT = Path(__file__).resolve().parent


def divider_test_scene(lay: model.Layout) -> Scene:
    t1 = next(t for t in lay.raw["temporary_wires"] if t["id"] == "T1")
    mk = next(m for m in lay.raw["markers"] if m["id"] == "MK5")
    return Scene(
        stage="B", title="Estagio B - passo 5: ENSAIO ESTATICO DO DIVISOR (sem o HC-SR04, sem o fio W4)",
        subtitle=(f"Jumper TEMPORARIO tracejado {t1['from']} -> {t1['to']} leva 5 V a R1. Meça entre o furo {mk['hole']} (no) e GND: "
                  "esperado ~2,8 V (aceitavel 2,50-3,20 V; NUNCA > 3,30 V)."),
        include_refs={"BB1", "U1", "R1", "R2", "R3", "W1", "W2"},
        temp_wires=[dict(t1)], markers=[dict(mk)], highlight_new=False)


def sha(path: Path) -> str:
    """SHA-256 do arquivo; para ZIP (.fzz/.fzpz) usa o conteudo dos membros (a compressao varia entre maquinas)."""
    if path.suffix in (".fzz", ".fzpz"):
        import zipfile
        h = hashlib.sha256()
        with zipfile.ZipFile(path) as z:
            for name in sorted(z.namelist()):
                h.update(name.encode() + b"\0" + hashlib.sha256(z.read(name)).digest())
        return h.hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(out_dir: Path, png: bool = False, wokwi_dir: Path | None = None) -> dict:
    lay = model.Layout.load()
    out_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    results = {}
    for st in model.STAGE_ORDER:
        issues = model.validate(lay, st)
        results[st] = {"errors": len(model.errors(issues)), "warnings": sum(i.level == "WARN" for i in issues)}
        if model.errors(issues):
            raise SystemExit(f"Estagio {st}: validacao falhou: " + "; ".join(map(str, model.errors(issues))))
        title = f"MotionPet - Estagio {st} - {lay.raw['stages'][st]['title']}"
        svg, _ = render_scene(lay, Scene(stage=st, title=title, subtitle=lay.raw["stages"][st]["goal"]))
        p = out_dir / f"protoboard_estagio{st}.svg"
        p.write_text(svg, encoding="utf-8"); files.append(p)
        p = out_dir / f"esquematico_estagio{st}.svg"
        p.write_text(render_schematic(lay, st, f"MotionPet - Esquematico eletrico - Estagio {st}"), encoding="utf-8"); files.append(p)
        p = out_dir / f"MotionPet_estagio{st}.fzz"
        export_fz.write_fzz(lay, st, str(p)); files.append(p)
        p = out_dir / f"fios_estagio{st}.csv"
        p.write_text(reports.to_csv(reports.wire_rows(lay, st)), encoding="utf-8"); files.append(p)
        p = out_dir / f"furos_estagio{st}.csv"
        p.write_text(reports.to_csv(reports.hole_map_rows(lay, st)), encoding="utf-8"); files.append(p)
        p = out_dir / f"estagio{st}.md"
        p.write_text(reports.stage_markdown(lay, st), encoding="utf-8"); files.append(p)
    # pecas genericas (importaveis no Fritzing: Arquivo > Importar) + .fzp soltos para o indice do MCP
    import zipfile
    from . import fz_parts
    (out_dir / "parts").mkdir(exist_ok=True)
    for spec in export_fz.generic_parts(lay).values():
        bundle = fz_parts.bundle_files(spec)
        pf = out_dir / "parts" / f"{spec.base}.fzp"
        pf.write_bytes(bundle[f"{spec.base}.fzp"]); files.append(pf)
        zf = out_dir / "parts" / f"{spec.base}.fzpz"
        with zipfile.ZipFile(zf, "w", zipfile.ZIP_DEFLATED) as z:
            for name in sorted(bundle):
                zi = zipfile.ZipInfo(name, date_time=(2026, 10, 29, 0, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(zi, bundle[name])
        files.append(zf)
    ts, _ = render_scene(lay, divider_test_scene(lay))
    p = out_dir / "protoboard_estagioB_passo5_ensaio_divisor.svg"
    p.write_text(ts, encoding="utf-8"); files.append(p)
    figs = {"B": [("Passo 5 — ensaio estatico do divisor (configuracao exata do teste)", ts)]}
    p = out_dir / "guia_montagem.html"
    p.write_text(guide_html.build_guide(lay, figs), encoding="utf-8"); files.append(p)
    p = out_dir / "netlist_resumo.md"
    p.write_text("# Netlist canonica (resumo gerado)\n\n" + "\n".join(
        f"## Estagio {st}\n\n" + reports.nets_md(lay, st) for st in model.STAGE_ORDER), encoding="utf-8"); files.append(p)
    wk = wokwi_dir or (ROOT / "wokwi")
    for name in export_wokwi.write_all(lay, wk):
        files.append(wk / name)
    if png:
        from .tools.svg2png import svg_to_png
        for svg in sorted(out_dir.glob("*.svg")):
            target = svg.with_suffix(".png")
            svg_to_png(svg, target, 1.6)
            files.append(target)
    def key(f: Path) -> str:
        if f.parent == out_dir:
            return f.name
        return "parts/" + f.name if f.parent.name == "parts" else "wokwi/" + str(f.relative_to(wk))
    manifest = {"validation": results, "files": {key(f): sha(f) for f in sorted(set(files)) if f.suffix != ".png"}}
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "out"))
    ap.add_argument("--png", action="store_true", help="tambem gera PNG (requer playwright + chromium)")
    a = ap.parse_args(argv)
    m = build(Path(a.out), png=a.png)
    for st, r in m["validation"].items():
        print(f"estagio {st}: {r['errors']} erros, {r['warnings']} avisos")
    print(f"{len(m['files'])} arquivos gerados em {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
