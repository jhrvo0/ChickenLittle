"""Parser JSON Lines estrito do firmware, rodando o jsonl_protocol.cpp real pela ponte de host."""
from __future__ import annotations

import ctypes
import json

import pytest

from tests.test_firmware_cycle3 import fw_lib  # noqa: F401  (fixture compartilhada)


def _env(data: str, v: str = "1", seq: str = "5", ts: str = "10", typ: str = '"pet_command"') -> str:
    return '{"v":%s,"seq":%s,"type":%s,"ts_ms":%s,"data":%s}' % (v, seq, typ, ts, data)


FEED = '{"command":"FEED","payload":{}}'

VALID = {
    "feed": _env(FEED),
    "feed com espacos": ' { "v" : 1 , "seq" : 5 , "type" : "pet_command" , "ts_ms" : 10 , "data" : {"command":"FEED"} } \r\n',
    "switch_mode payload": _env('{"command":"SWITCH_MODE","payload":{"mode":"AIR_MUSIC"}}'),
    "play launch match": _env('{"command":"PLAY","payload":{"minigame":"PET_LAUNCH","action":"MATCH_RESULT","distance_m":64.5,"score":980,"coins_earned":18,"xp_earned":25,"bounces":2}}'),
    "play launch upgrade": _env('{"command":"PLAY","payload":{"minigame":"PET_LAUNCH","action":"UNLOCK_UPGRADE","upgrade_id":"SLINGSHOT_PRO","cost":15}}'),
    "set_period em data": _env('{"command":"SET_PERIOD","period_ms":70}'),
    "set_period em payload": _env('{"command":"SET_PERIOD","payload":{"period_ms":70}}'),
    "set_ir": _env('{"command":"SET_IR","payload":{"enabled":false}}'),
    "start_collection": _env('{"command":"START_COLLECTION","period_ms":80}'),
    "gesture": _env('{"gesture":"APPROACH","confidence":0.94,"source":"tinyml","window_ms":600}', typ='"gesture_event"'),
    "gesture conf 1e-05": _env('{"gesture":"HOLD","confidence":1e-05}', typ='"gesture_event"'),
    "lcd": _env(json.dumps({"lines": ['A "q" and \\'.ljust(20), "B" * 20, "C" * 20, "D" * 20]}), typ='"lcd_frame"'),
    "bench DIAG": "DIAG",
    "bench PERIOD": "PERIOD 70",
    "bench IR ON": "IR ON",
}

INVALID = {
    # chaves só valem no objeto certo
    "seq aninhado": '{"v":1,"type":"pet_command","ts_ms":10,"data":{"command":"FEED","meta":{"seq":9}}}',
    "seq so dentro de data": '{"v":1,"type":"pet_command","ts_ms":10,"data":{"command":"FEED","seq":9}}',
    "type so em data": '{"v":1,"seq":1,"ts_ms":10,"data":{"type":"pet_command","command":"FEED"}}',
    "data aninhado em objeto extra": '{"v":1,"seq":1,"type":"pet_command","ts_ms":1,"x":{"data":{"command":"FEED"}}}',
    "command so em payload": _env('{"payload":{"command":"FEED"}}'),
    "gesture em payload": _env('{"payload":{"gesture":"HOLD","confidence":0.5}}', typ='"gesture_event"'),
    "lines em subobjeto": _env('{"x":{"lines":["A","B","C","D"]}}', typ='"lcd_frame"'),
    "chave duplicada seq": '{"v":1,"seq":1,"seq":2,"type":"pet_command","ts_ms":10,"data":{"command":"FEED"}}',
    # inteiros estritos
    "seq 1e2": _env(FEED, seq="1e2"),
    "seq 12abc": _env(FEED, seq="12abc"),
    "ts_ms 1.5": _env(FEED, ts="1.5"),
    "v 1e0": _env(FEED, v="1e0"),
    "seq -1": _env(FEED, seq="-1"),
    "seq 007": _env(FEED, seq="007"),
    "seq overflow": _env(FEED, seq="4294967296"),
    "period_ms 7e1": _env('{"command":"SET_PERIOD","period_ms":7e1}'),
    "period_ms 70x": _env('{"command":"SET_PERIOD","period_ms":70x}'),
    "bench PERIOD 12abc": "PERIOD 12abc",
    "bench PERIOD overflow": "PERIOD 99999999999",
    # sintaxe JSON
    "virgula faltando entre campos": '{"v":1 "seq":1,"type":"pet_command","ts_ms":10,"data":{"command":"FEED"}}',
    "virgula faltando antes de data": '{"v":1,"seq":1,"type":"pet_command","ts_ms":10 "data":{"command":"FEED"}}',
    "dois-pontos faltando": '{"v":1,"seq":1,"type":"pet_command","ts_ms":10,"data":{"command" "FEED"}}',
    "dois-pontos faltando no envelope": '{"v" 1,"seq":1,"type":"pet_command","ts_ms":10,"data":{"command":"FEED"}}',
    "virgula sobrando": '{"v":1,"seq":1,"type":"pet_command","ts_ms":10,"data":{"command":"FEED",}}',
    "dois objetos colados": _env(FEED) + _env(FEED),
    "lixo apos objeto": _env(FEED) + "  x",
    "chave sem aspas": '{"v":1,"seq":1,type:"pet_command","ts_ms":10,"data":{"command":"FEED"}}',
    "escape invalido": _env('{"command":"FE\\qED"}'),
    "profundidade excessiva": _env('{"command":"FEED","p":' + '{"a":' * 9 + "1" + "}" * 9 + "}"),
    # campos opcionais e strings
    "window_ms invalido": _env('{"gesture":"HOLD","confidence":0.5,"window_ms":"x"}', typ='"gesture_event"'),
    "confidence 1x": _env('{"gesture":"HOLD","confidence":1x}', typ='"gesture_event"'),
    "mode longo demais": _env('{"command":"SWITCH_MODE","payload":{"mode":"ABCDEFGHIJKLMNOPQRSTUVWXYZ"}}'),
}


class _Out:
    def __init__(self) -> None:
        self.kind = ctypes.c_int32()
        self.seq = ctypes.c_uint32()
        self.pcmd = ctypes.c_int32()
        self.p32 = ctypes.c_uint32()
        self.pbool = ctypes.c_int32()
        self.mode = ctypes.create_string_buffer(24)
        self.err = ctypes.create_string_buffer(24)


def _parse(lib: ctypes.CDLL, line: str) -> tuple[bool, _Out]:
    lib.fw_jsonl_reset()
    o = _Out()
    ok = bool(lib.fw_jsonl_parse_line(
        line.encode(), ctypes.byref(o.kind), ctypes.byref(o.seq), ctypes.byref(o.pcmd),
        ctypes.byref(o.p32), ctypes.byref(o.pbool), o.mode, 24, o.err, 24,
    ))
    return ok, o


@pytest.mark.parametrize("line", VALID.values(), ids=VALID.keys())
def test_strict_parser_accepts_commands_the_app_sends(fw_lib: ctypes.CDLL, line: str) -> None:
    ok, o = _parse(fw_lib, line)
    assert ok, o.err.value.decode()


@pytest.mark.parametrize("line", INVALID.values(), ids=INVALID.keys())
def test_strict_parser_rejects_malformed_lines(fw_lib: ctypes.CDLL, line: str) -> None:
    ok, o = _parse(fw_lib, line)
    assert not ok
    assert o.err.value, "linha rejeitada deve trazer código de erro"


def test_strict_parser_extracts_parameters(fw_lib: ctypes.CDLL) -> None:
    ok, o = _parse(fw_lib, VALID["switch_mode payload"])
    assert ok and o.mode.value == b"AIR_MUSIC" and o.seq.value == 5
    ok, o = _parse(fw_lib, VALID["set_period em payload"])
    assert ok and o.p32.value == 70 and o.kind.value == 5
    ok, o = _parse(fw_lib, VALID["set_ir"])
    assert ok and o.pbool.value == 0 and o.kind.value == 6
    ok, o = _parse(fw_lib, VALID["start_collection"])
    assert ok and o.p32.value == 80 and o.kind.value == 3
