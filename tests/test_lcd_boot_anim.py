"""Valida a animacao de boot do LCD (firmware/display/lcd2004_anim.cpp).

Confere, a partir do fonte C: cada linha de texto cabe em 20 colunas e e ASCII imprimivel,
o sprite usa as colunas validas, cada quadro dura pelo menos 250 ms (<= 4 quadros/s),
o total fica em ate 3 s, e os glifos tem 4 celulas de 8 linhas com 5 bits.
"""

import re
from pathlib import Path

ANIM_CPP = Path(__file__).resolve().parents[1] / "firmware" / "display" / "lcd2004_anim.cpp"

STR = r'(NULL|"(?:[^"\\]|\\.)*")'
FRAME_RE = re.compile(
    r'\{\s*' + STR + r'\s*,\s*(BOOT_SPR_\w+)\s*,\s*(\d+)U\s*,\s*' + STR + r'\s*,\s*(\d+)U\s*\}'
)
GLYPH_RE = re.compile(r'static const uint8_t (k\w+Glyphs)\[4\]\[8\] = \{(.*?)\};', re.S)


def _c_literal(tok: str) -> str:
    body = tok[1:-1]
    assert re.fullmatch(r'(?:[^\\]|\\\\|\\")*', body), f"escape nao suportado: {tok}"
    return body.replace('\\\\', '\\').replace('\\"', '"')


def _src() -> str:
    return ANIM_CPP.read_text(encoding="utf-8")


def _frames():
    src = _src()
    block = src[src.index("kBootFrames[] = {"):]
    block = block[: block.index("};")]
    return FRAME_RE.findall(block)


def test_boot_frames_fit_lcd_and_timing():
    frames = _frames()
    assert len(frames) >= 5
    sprites_ok = {"BOOT_SPR_NONE", "BOOT_SPR_EGG", "BOOT_SPR_CRACK", "BOOT_SPR_CHICK"}
    total_ms = 0
    for row0, sprite, x0, row3, hold in frames:
        assert sprite in sprites_ok, sprite
        assert 0 <= int(x0) <= 18, f"sprite fora da tela: x0={x0}"
        for tok in (row0, row3):
            if tok == "NULL":
                continue
            text = _c_literal(tok)
            assert len(text) <= 20, repr(text)
            assert all(0x20 <= ord(ch) <= 0x7E for ch in text), repr(text)
        assert int(hold) >= 250, f"quadro muito rapido: {hold} ms"  # no maximo 4 quadros/s
        total_ms += int(hold)
    assert total_ms <= 3000, f"animacao longa demais: {total_ms} ms"


def test_sprite_glyphs_have_4_cells_of_8_rows_with_5_bits():
    glyph_sets = dict(GLYPH_RE.findall(_src()))
    assert {"kEggGlyphs", "kCrackGlyphs", "kChickGlyphs"} <= set(glyph_sets)
    for name, body in glyph_sets.items():
        cells = re.findall(r'\{([^}]*)\}', body)
        assert len(cells) == 4, name
        for cell in cells:
            values = [int(v, 16) for v in re.findall(r'0x[0-9A-Fa-f]+', cell)]
            assert len(values) == 8, name
            assert all(0 <= v <= 0x1F for v in values), name
