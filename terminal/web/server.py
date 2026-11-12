"""Servidor gráfico local: .venv/Scripts/python.exe -m terminal.web."""
from __future__ import annotations

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from urllib.parse import parse_qs, urlsplit

from terminal.web.session import MotionPetSession
from terminal.web.ml_client import MlApiClient

STATIC = Path(__file__).parent / "static"
_HTML, _JS, _CSS = "text/html; charset=utf-8", "text/javascript; charset=utf-8", "text/css; charset=utf-8"
# Lista fechada de arquivos servidos (nada de caminho vindo do pedido chega ao disco).
STATIC_FILES = {
    "/": ("index.html", _HTML), "/index.html": ("index.html", _HTML),
    "/lab.css": ("lab.css", _CSS), "/lab.js": ("lab.js", _JS), "/canvas.js": ("canvas.js", _JS),
    "/music.js": ("music.js", _JS), "/intel.js": ("intel.js", _JS),
    # Experiência anterior (pet e Pet Launch), mantida por compatibilidade.
    "/legacy": ("legacy/index.html", _HTML), "/legacy/": ("legacy/index.html", _HTML),
    "/legacy/index.html": ("legacy/index.html", _HTML),
    "/legacy/app.css": ("legacy/app.css", _CSS), "/legacy/app.js": ("legacy/app.js", _JS),
}


def _int_param(query: dict, name: str) -> int:
    try:
        value = int(query.get(name, ["0"])[0])
    except ValueError:
        return 0
    return max(0, value)


class MotionPetServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int = 8767, *, allow_demo: bool = False, host="127.0.0.1", ml_api_url=None):
        self.api_key = secrets.token_urlsafe(24)
        self.ml_api = MlApiClient(ml_api_url)
        self.session = MotionPetSession(allow_demo=allow_demo)
        try:
            super().__init__((host, port), MotionPetHandler)
        except Exception:
            self.session.close()
            raise
        self.origin = f"http://127.0.0.1:{self.server_port}"

    def server_close(self) -> None:
        super().server_close()
        self.session.close()


class MotionPetHandler(BaseHTTPRequestHandler):
    server: MotionPetServer

    def log_message(self, *_args) -> None:
        pass

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(6)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value: dict) -> None:
        self._send(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"), "application/json; charset=utf-8")

    def _allowed(self, *, api: bool) -> bool:
        if self.headers.get("Host") != self.server.origin.removeprefix("http://"):
            self._json(403, {"ok": False, "error": "Use o endereço local informado pelo aplicativo."})
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin != self.server.origin:
            self._json(403, {"ok": False, "error": "Origem externa não permitida."})
            return False
        if api and not hmac.compare_digest(self.headers.get("X-MotionPet-Key", "").encode(), self.server.api_key.encode()):
            self._json(403, {"ok": False, "error": "Reabra a página do MotionPet para habilitar a conexão."})
            return False
        return True

    def do_GET(self) -> None:
        parts = urlsplit(self.path)
        path = parts.path
        if not self._allowed(api=path.startswith("/api/")):
            return
        if path == "/api/state":
            self._json(200, self.server.session.state())
        elif path == "/api/ports":
            self._json(200, {"ports": self.server.session.ports()})
        elif path == "/api/live":
            query = parse_qs(parts.query)
            self._json(200, self.server.session.live(_int_param(query, "f"), _int_param(query, "e")))
        elif path == "/api/lab":
            self._json(200, self.server.session.lab_state())
        elif path in ("/api/ml/status", "/api/ml/evaluations", "/api/ml/predictions"):
            code, data = self.server.ml_api.request(path.rsplit("/", 1)[1])
            self._json(code, data)
        elif path == "/health":
            self._json(200, {"status": "ready", "schema_version": 1})
        elif path in STATIC_FILES:
            name, mime = STATIC_FILES[path]
            try:
                data = (STATIC / name).read_bytes()
            except OSError:
                self._json(503, {"ok": False, "error": "Interface ainda indisponível."})
                return
            if name.endswith("index.html"):
                data = data.decode("utf-8").replace("</head>", f'<meta name="motionpet-key" content="{self.server.api_key}"></head>', 1).encode("utf-8")
            self._send(200, data, mime)
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        else:
            self._json(404, {"ok": False, "error": "Página não encontrada."})

    def do_POST(self) -> None:
        if not self._allowed(api=True):
            return
        try:
            path = urlsplit(self.path).path
            if path not in {"/api/connect", "/api/disconnect", "/api/action", "/api/lab", "/api/experience", "/api/ml/infer"}:
                self._json(404, {"ok": False, "error": "Ação não encontrada."})
                return
            if self.headers.get("Transfer-Encoding") is not None:
                raise ValueError("Formato de pedido inválido.")
            length = int(self.headers.get("Content-Length", "0"))
            limit = 65536 if path == "/api/ml/infer" else 16384
            if not 0 < length <= limit:
                if length > limit:
                    self.rfile.read(min(length, limit + 1))
                raise ValueError("Pedido vazio ou grande demais.")
            if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                raise ValueError("Envie os comandos como JSON.")
            def invalid_number(value):
                raise ValueError("Número inválido.")
            payload = json.loads(self.rfile.read(length).decode("utf-8"), parse_constant=invalid_number)
            if not isinstance(payload, dict):
                raise ValueError("Comando inválido.")
            if path == "/api/ml/infer":
                code, data = self.server.ml_api.request("infer", payload)
                self._json(code, data)
                return
            elif path == "/api/connect":
                self.server.session.connect(payload.get("port"))
            elif path == "/api/disconnect":
                self.server.session.disconnect()
            elif path == "/api/lab":
                self._json(200, {"ok": True, "lab": self.server.session.lab(payload)})
                return
            elif path == "/api/experience":
                self.server.session.set_experience(payload.get("value"))
            else:
                self.server.session.action(payload)
            self._json(200, {"ok": True, "state": self.server.session.state()})
        except (ValueError, TypeError, UnicodeDecodeError) as exc:
            self._json(400, {"ok": False, "error": str(exc)})

    def do_OPTIONS(self) -> None:
        self._json(403, {"ok": False, "error": "Use a interface local do MotionPet."})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--host", default="127.0.0.1", help="0.0.0.0 somente no container; porta publicada no loopback.")
    parser.add_argument("--ml-api-url", help="Serviço ML configurado pelo operador; frontend usa /api/ml/*.")
    parser.add_argument("--demo", action="store_true", help="Disponibiliza uma demonstração identificada, sem sensores reais.")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("Porta inválida.")
    server = MotionPetServer(args.port, allow_demo=args.demo, host=args.host, ml_api_url=args.ml_api_url)
    print(f"MotionLab: {server.origin}/   (experiência anterior do pet: {server.origin}/legacy/)", flush=True)
    print("Feche o monitor serial antes de conectar a ESP32 pela interface. Ctrl+C encerra.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
