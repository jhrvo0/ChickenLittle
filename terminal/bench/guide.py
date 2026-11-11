"""Guia de bancada local com testes reais pela USB, sem gravacao automatica.

Iniciar na raiz: .venv/Scripts/python.exe -m terminal.bench.guide
"""
from __future__ import annotations

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import secrets
import threading
from typing import Any
from urllib.parse import urlsplit

from terminal.bench.assistant import (
    DEFAULT_BENCH_LOG_PATH,
    inspect_telemetry_stream,
    list_serial_ports,
    query_device_diag,
    record_bench_log_entry,
)
from terminal.communication.transport import PySerialEndpoint

ROOT = Path(__file__).resolve().parents[2]
GUIDE_HTML_PATH = ROOT / "hardware" / "guia_montagem_final.html"
COMPONENTS = {"esp32", "lcd", "ir", "hcsr04", "all"}
MAX_BODY_BYTES = 8192


class RequestError(ValueError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def validate_request(data: Any) -> dict:
    """Aceita somente os campos do guia; nunca converte strings/bools em medicoes."""
    if not isinstance(data, dict) or set(data) - {"component", "port", "measurements", "confirmations"}:
        raise RequestError("Pedido invalido: informe componente, porta, medicoes e confirmacoes do guia.")
    component, port = data.get("component"), data.get("port")
    if not isinstance(component, str) or component not in COMPONENTS:
        raise RequestError("Componente invalido.")
    if not isinstance(port, str) or not port or len(port) > 128:
        raise RequestError("Selecione uma porta USB listada no guia.")
    measures, confirms = data.get("measurements", {}), data.get("confirmations", {})
    if not isinstance(measures, dict) or set(measures) - {"supply_3v3", "echo_v", "reference_cm"}:
        raise RequestError("Campos de medicao invalidos.")
    if not isinstance(confirms, dict) or set(confirms) - {"wiring", "lcd_visual"}:
        raise RequestError("Campos de confirmacao invalidos.")
    normalized_measures = {}
    for key in ("supply_3v3", "echo_v", "reference_cm"):
        value = measures.get(key)
        try:
            finite_number = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            finite_number = False
        if value is not None and not finite_number:
            raise RequestError(f"{key}: informe um numero finito medido, ou deixe vazio.")
        normalized_measures[key] = float(value) if value is not None else None
    for key in ("wiring", "lcd_visual"):
        if key in confirms and type(confirms[key]) is not bool:
            raise RequestError(f"{key}: confirmacao deve ser verdadeira ou falsa.")
    return {"component": component, "port": port, "measurements": normalized_measures,
            "confirmations": {key: confirms.get(key, False) for key in ("wiring", "lcd_visual")}}


def _result(status: str, summary: str, problems: list[str], details: dict, next_action: str) -> dict:
    return {"status": status, "summary": summary, "problems": problems, "details": details,
            "next_action": next_action, "validation_origin": "PHYSICAL_ESP32"}


def run_physical_test(data: dict, log_path: str | Path = DEFAULT_BENCH_LOG_PATH) -> dict:
    """Captura apenas hardware. Ausencia de evidencia manual permanece pendente."""
    data = validate_request(data)
    component = data["component"]
    if data["port"] not in {p.device for p in list_serial_ports()}:
        raise RequestError("A porta selecionada nao esta conectada. Atualize a lista e confira o cabo USB.")
    measures, confirms = data["measurements"], data["confirmations"]
    details: dict[str, Any] = {"component": component, "port": data["port"], "captured": False,
                              "operator_measurements": measures, "operator_confirmations": confirms,
                              "automatic_voltage_measurement": False,
                              "echo_measurement_kind": "operator_static_divider_test_not_echo_peak"}
    needs_us, needs_3v3 = component in ("hcsr04", "all"), component in ("lcd", "ir", "all")
    preflight: list[str] = []
    missing: list[str] = []
    if needs_3v3 and measures["supply_3v3"] is not None and not 3.0 <= measures["supply_3v3"] <= 3.35:
        preflight.append("VCC informado fora do perfil 3V3 (3,00..3,35 V). LCD I2C direto e TCRT5000 nao usam 5 V.")
    if needs_us:
        if measures["echo_v"] is None:
            missing.append("Informe a tensao medida no ensaio estatico do divisor, antes de conectar GPIO34.")
        elif not 2.5 <= measures["echo_v"] <= 3.30:
            preflight.append("Divisor fora da faixa 2,50..3,30 V: mantenha GPIO34 desconectado e reveja a montagem.")
        if measures["reference_cm"] is None:
            missing.append("Informe a distancia real do alvo ao HC-SR04 (2..400 cm).")
        elif not 2.0 <= measures["reference_cm"] <= 400.0:
            preflight.append("A distancia de referencia deve ficar entre 2 e 400 cm.")
        if not confirms["wiring"]:
            missing.append("Confira o divisor e os fios antes de autorizar a captura do HC-SR04.")
    if preflight or missing:
        result = _result("failed" if preflight else "pending", "Captura nao iniciada: confira os dados da montagem.",
                         preflight + missing, details, "Desligue a USB para corrigir fios; informe apenas medidas reais.")
        record_bench_log_entry("GUIDE_" + component.upper(), "PHYSICAL_ESP32", False, result,
                               result["problems"], log_path)
        return result

    endpoint = None
    try:
        endpoint = PySerialEndpoint(data["port"], baudrate=115200)
        # Algumas placas reiniciam ao abrir a USB; a animacao de boot antecede a task serial.
        try:
            diag = query_device_diag(endpoint, timeout_sec=4.0)
        except TimeoutError:
            diag = query_device_diag(endpoint, timeout_sec=3.0)
        details["diag"] = diag.to_dict()
        if not diag.is_physical_hardware:
            result = _result("failed", "A origem recebida nao identifica uma ESP32 fisica com o firmware MotionPet.",
                           [f"DIAG informou origin={diag.origin}. Simulacao nao aprova a montagem."], details,
                           "Grave o firmware da pasta firmware na placa real e repita o teste.")
            record_bench_log_entry("GUIDE_" + component.upper(), "PHYSICAL_ESP32", False, result,
                                   result["problems"], log_path)
            return result
        endpoint.write_line("START")
        if component in ("ir", "all"):
            endpoint.write_line("IR ON")
        stream = inspect_telemetry_stream(
            endpoint, duration_sec=8.0 if component in ("ir", "all") else 2.5,
            expected_period_ms=diag.sample_period_ms,
            reference_cm=measures["reference_cm"] if needs_us else None,
            validation_origin="PHYSICAL_ESP32",
        )
    except Exception as exc:
        result = _result("failed", "Nao foi possivel obter a telemetria da placa.", [str(exc)], details,
                         "Feche monitores seriais, confira a porta/cabo e grave o firmware integrado (os testes isolados nao respondem DIAG JSONL).")
        record_bench_log_entry("GUIDE_" + component.upper(), "PHYSICAL_ESP32", False, result,
                               result["problems"], log_path)
        return result
    finally:
        if endpoint is not None:
            endpoint.close()

    details["captured"] = True
    details["telemetry"] = stream.to_dict()
    details["device_lcd_20x4"] = list(stream.last_lcd_lines)
    problems: list[str] = []
    pending: list[str] = []
    if stream.sensor_frames_count < 3:
        problems.append("Menos de tres sensor_frame recebidos; confira o firmware integrado e a serial.")
    if stream.parse_errors:
        problems.append(f"Erros de JSONL recebidos: {stream.parse_errors}.")
    if stream.seq_gaps_detected:
        problems.append(f"Pacotes perdidos na serial: {stream.seq_gaps_detected}.")
    if stream.sensor_frames_count >= 3 and not stream.period_within_tolerance:
        problems.append("O periodo de amostragem recebido divergiu do informado em DIAG.")
    if diag.free_heap_bytes < 32768:
        problems.append("A placa informou menos de 32 KiB de memoria heap livre.")
    if component in ("lcd", "all"):
        if not (stream.lcd_frames_count > 0 and len(stream.last_lcd_lines) == 4
                and all(len(row) == 20 for row in stream.last_lcd_lines)):
            problems.append("Nenhum quadro LCD valido de 4 linhas x 20 colunas foi recebido.")
        if not confirms["lcd_visual"]:
            pending.append("Compare o LCD fisico com as quatro linhas recebidas e confirme a imagem no guia.")
    if component in ("ir", "all") and not (
            stream.ir_true_count > 0 and stream.ir_false_count > 0 and stream.ir_transitions > 0):
        problems.append("IR sem alternancia observada: aproxime e afaste um cartao durante os 8 segundos de captura.")
    if needs_us:
        if stream.valid_ultrasonic_count < 3 or stream.timeout_ratio > 0.35:
            problems.append("Poucas distancias validas ou mais de 35% de timeouts; confira alvo, 5V, TRIG e divisor.")
        if stream.reference_within_tolerance is not True:
            problems.append("A distancia recebida nao acompanhou a referencia informada.")
    # Antes da instalacao do HC-SR04, seus timeouts sao esperados e nao reprovam LCD/IR/ESP32.
    details["ultrasonic_required"] = needs_us
    if needs_3v3 and measures["supply_3v3"] is None:
        pending.append("Falta informar a tensao realmente medida em VCC do modulo (perfil 3V3).")
    if component != "esp32" and not confirms["wiring"]:
        pending.append("Falta a confirmacao de conferencia dos fios pelo operador.")
    status = "failed" if problems else "pending" if pending else "passed"
    labels = {"esp32": "Comunicacao ESP32", "lcd": "LCD", "ir": "TCRT5000", "hcsr04": "HC-SR04", "all": "Conjunto"}
    suffix = {"passed": "verificado conforme telemetria e confirmacoes fornecidas.",
              "pending": "com telemetria observada; faltam conferencias manuais.",
              "failed": "com falha observada; veja os detalhes."}[status]
    next_action = ("Desligue a USB antes de adicionar o proximo componente." if status == "passed" else
                   "Complete as conferencias pendentes e repita; a serial nao mede tensoes nem enxerga o LCD." if status == "pending" else
                   "Confira as causas listadas; desligue a USB antes de corrigir a montagem.")
    result = _result(status, f"{labels[component]} {suffix}", problems + pending, details, next_action)
    record_bench_log_entry("GUIDE_" + component.upper(), "PHYSICAL_ESP32", status == "passed", result,
                           result["problems"], log_path)
    return result


class GuideServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int = 8766, log_path: str | Path = DEFAULT_BENCH_LOG_PATH) -> None:
        self.api_key = secrets.token_urlsafe(32)
        self.capture_lock = threading.Lock()
        self.log_path = log_path
        super().__init__(("127.0.0.1", port), GuideHandler)

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


class GuideHandler(BaseHTTPRequestHandler):
    server: GuideServer

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(15.0)

    def log_message(self, format: str, *args: Any) -> None:
        # Nao registra query strings ou cabecalhos de autenticacao.
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, status: int, data: dict) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _allowed(self, api: bool = False) -> bool:
        if self.headers.get("Host") != self.server.origin.removeprefix("http://"):
            self._json(403, {"error": "Use o endereco local 127.0.0.1 informado pelo guia."})
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin != self.server.origin:
            self._json(403, {"error": "Origem externa nao permitida."})
            return False
        if api and not hmac.compare_digest(self.headers.get("X-MotionPet-Key", "").encode("utf-8"),
                                           self.server.api_key.encode("ascii")):
            self._json(403, {"error": "Abra novamente o guia pelo endereco local para habilitar os testes."})
            return False
        return True

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if not self._allowed(api=path.startswith("/api/")):
            return
        if path in ("/", "/guia_montagem_final.html", "/hardware/guia_montagem_final.html"):
            try:
                page = GUIDE_HTML_PATH.read_text(encoding="utf-8")
            except OSError:
                self._json(503, {"error": "Guia indisponivel. Gere os arquivos com python -m hardware.final_assembly pelo ambiente do projeto."})
                return
            page = page.replace("</head>", f'<meta name="motionpet-key" content="{self.server.api_key}"></head>', 1)
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/ports":
            self._json(200, {"ports": [{"device": p.device, "description": p.description} for p in list_serial_ports()]})
        elif path in ("/docs/bench_assembly_guide.md", "/docs/hardware_safety.md", "/docs/cycle5_bench_checklist.md"):
            self._send(200, (ROOT / path.lstrip("/")).read_bytes(), "text/plain; charset=utf-8")
        else:
            self._json(404, {"error": "Recurso nao disponivel no guia."})

    def do_POST(self) -> None:
        if not self._allowed(api=True):
            return
        if urlsplit(self.path).path != "/api/test":
            self._json(404, {"error": "Acao nao disponivel no guia."})
            return
        if self.headers.get("Transfer-Encoding") is not None:
            self._json(400, {"error": "Formato de pedido nao suportado."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY_BYTES:
                # Evita reset TCP no Windows ao fechar com um corpo pequeno ainda
                # pendente; o cliente deve receber a resposta 413. Leitura limitada.
                if length > MAX_BODY_BYTES:
                    self.rfile.read(min(length, MAX_BODY_BYTES + 1))
                raise RequestError("Pedido vazio ou grande demais.", 413)
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
                raise RequestError("Envie dados no formato JSON.", 415)
            def reject_constant(value: str) -> None:
                raise ValueError(f"Numero JSON invalido: {value}")
            payload = validate_request(json.loads(self.rfile.read(length).decode("utf-8"), parse_constant=reject_constant))
        except (ValueError, UnicodeDecodeError) as exc:
            self._json(exc.status if isinstance(exc, RequestError) else 400, {"error": str(exc)})
            return
        if not self.server.capture_lock.acquire(blocking=False):
            self._json(409, {"error": "Ja existe um teste USB em andamento. Aguarde seu resultado."})
            return
        try:
            self._json(200, run_physical_test(payload, log_path=self.server.log_path))
        except RequestError as exc:
            self._json(exc.status, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": f"Falha no teste local: {exc}"})
        finally:
            self.server.capture_lock.release()

    def do_OPTIONS(self) -> None:
        self._json(403, {"error": "Use os botoes do proprio guia local."})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766, help="Porta HTTP local (padrao: 8766).")
    parser.add_argument("--log-path", default=str(DEFAULT_BENCH_LOG_PATH), help="Historico JSON das verificacoes.")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port deve ficar entre 0 e 65535")
    try:
        server = GuideServer(args.port, args.log_path)
    except OSError as exc:
        parser.exit(1, f"Nao foi possivel iniciar o guia local: {exc}. Escolha outra --port.\n")
    print(f"Guia com testes USB: {server.origin}/", flush=True)
    print("Desligue a USB para mudar fios. Ctrl+C encerra o servico local.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
