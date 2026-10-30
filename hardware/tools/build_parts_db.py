"""Indexa um checkout do fritzing-parts em um parts.db (SQLite) compativel com o `fzkit.partsdb` do fritzing-mcp.

Por que existe: o fritzing-mcp espera `<FRITZING_APP_ROOT>/parts/parts.db`, gerado pelo aplicativo Fritzing.
Sem o aplicativo instalado, este script cria um indice EQUIVALENTE (nao e o parts.db oficial) a partir dos .fzp.

Esquema (lido de fzkit/partsdb.py, apenas como DADO): parts(id, moduleID, title, label, family, path),
tags(part_id, tag), connectors(part_id, connectorid, name, type) com type 0=male, 1=female, 2=pad.

Uso:
  python -m hardware.tools.build_parts_db <fritzing-parts-dir> <saida/parts/parts.db> [--extra-fzp arquivo.fzp ...]
Codigo proprio, apenas biblioteca padrao.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SCHEMA = """
CREATE TABLE parts (id INTEGER PRIMARY KEY, moduleID TEXT UNIQUE, title TEXT, label TEXT, family TEXT, path TEXT);
CREATE TABLE tags (part_id INTEGER, tag TEXT);
CREATE TABLE connectors (part_id INTEGER, connectorid TEXT, name TEXT, type INTEGER);
CREATE INDEX idx_parts_module ON parts(moduleID);
"""
TYPE_CODE = {"male": 0, "female": 1, "pad": 2}


def index_fzp(con: sqlite3.Connection, fzp: Path, rel: str) -> bool:
    try:
        root = ET.parse(fzp).getroot()
    except ET.ParseError:
        return False
    module_id = root.get("moduleId")
    if not module_id:
        return False
    family = ""
    props = root.find("properties")
    if props is not None:
        for p in props.findall("property"):
            if (p.get("name") or "").lower() == "family":
                family = (p.text or p.get("value") or "").strip()
    cur = con.execute("INSERT OR IGNORE INTO parts(moduleID, title, label, family, path) VALUES (?,?,?,?,?)",
                      (module_id, root.findtext("title", ""), root.findtext("label", ""), family, rel))
    if cur.rowcount == 0:
        return False
    pid = cur.lastrowid
    for tag in root.findall("tags/tag"):
        if tag.text:
            con.execute("INSERT INTO tags(part_id, tag) VALUES (?,?)", (pid, tag.text.strip()))
    conns = root.find("connectors")
    if conns is not None:
        for c in conns.findall("connector"):
            con.execute("INSERT INTO connectors(part_id, connectorid, name, type) VALUES (?,?,?,?)",
                        (pid, c.get("id"), c.get("name", ""), TYPE_CODE.get(c.get("type", "male"), 0)))
    return True


def build(parts_dir: Path, out_db: Path, extra: list[Path] | None = None) -> int:
    out_db.parent.mkdir(parents=True, exist_ok=True)
    if out_db.exists():
        out_db.unlink()
    con = sqlite3.connect(out_db)
    con.executescript(SCHEMA)
    n = 0
    for sub in ("core", "contrib", "user"):
        d = parts_dir / sub
        if not d.is_dir():
            continue
        for fzp in sorted(d.glob("*.fzp")):
            n += index_fzp(con, fzp, f"{sub}/{fzp.name}")
    for fzp in extra or []:
        n += index_fzp(con, fzp, f"user/{fzp.name}")
    con.commit()
    con.close()
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("parts_dir", type=Path)
    ap.add_argument("out_db", type=Path)
    ap.add_argument("--extra-fzp", type=Path, nargs="*", default=[])
    a = ap.parse_args(argv)
    n = build(a.parts_dir, a.out_db, a.extra_fzp)
    print(f"{n} partes indexadas em {a.out_db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
