"""Prepara (NAO executa automaticamente) o MCP de Fritzing escolhido, de forma ISOLADA em ./tools/.

Escolha: fedoragobrowse-design/fritzing-mcp (MIT), fixado no commit abaixo. Nada e instalado globalmente.
Cada comando externo e IMPRESSO antes de rodar; use --dry-run para so ver. Requer: git, uv (https://docs.astral.sh/uv/).

  python -m hardware.tools.setup_fritzing_mcp --dry-run
  python -m hardware.tools.setup_fritzing_mcp --parts-dir <checkout do fritzing-parts>   # ou omita para clonar (grande: ~370 MB)

STATUS: preparado, mas NAO verificado no ambiente de geracao (execucao de codigo externo foi negada ali).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_URL = "https://github.com/fedoragobrowse-design/fritzing-mcp.git"
PINNED_COMMIT = "3a8c7ca9b4b9ec52f356070670c05c651f096c24"     # 2026-09-13, MIT, revisado manualmente (sem rede/exec arbitrario)
PARTS_URL = "https://github.com/fritzing/fritzing-parts.git"
ROOT = Path(__file__).resolve().parents[2]


def run(cmd: list[str], dry: bool, cwd: Path | None = None) -> None:
    print("$", " ".join(cmd), f"(cwd={cwd})" if cwd else "")
    if not dry:
        subprocess.run(cmd, check=True, cwd=cwd)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", type=Path, default=ROOT / "tools")
    ap.add_argument("--parts-dir", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    mcp_dir = a.dest / "fritzing-mcp"
    app_root = a.dest / "fritzing_root"
    if not mcp_dir.exists():
        run(["git", "clone", REPO_URL, str(mcp_dir)], a.dry_run)
    run(["git", "checkout", "--detach", PINNED_COMMIT], a.dry_run, cwd=mcp_dir)
    if not a.dry_run:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=mcp_dir, capture_output=True, text=True, check=True).stdout.strip()
        if head != PINNED_COMMIT:
            print(f"ERRO: HEAD={head} != {PINNED_COMMIT}", file=sys.stderr)
            return 2
    run(["uv", "sync"], a.dry_run, cwd=mcp_dir)             # usa o uv.lock do projeto (dependencias travadas)
    parts = a.parts_dir or (a.dest / "fritzing-parts")
    if a.parts_dir is None and not parts.exists():
        run(["git", "clone", "--depth", "1", PARTS_URL, str(parts)], a.dry_run)
    cmd = [sys.executable, "-m", "hardware.tools.build_parts_db", str(parts), str(app_root / "parts" / "parts.db")]
    gen = sorted((ROOT / "hardware" / "out" / "parts").glob("MotionPet_*.fzp"))
    run(cmd + (["--extra-fzp", *map(str, gen)] if gen else []), a.dry_run, cwd=ROOT)
    print("\nPronto. Abra o Claude Code na raiz do repositorio: o .mcp.json define o servidor 'fritzing'.\n"
          "Confirme com:  claude mcp list   e, dentro do Claude Code, /mcp  (aprove o servidor do projeto).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
