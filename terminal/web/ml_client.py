"""Proxy fechado para a API acadêmica; indisponibilidade não bloqueia o MotionLab."""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


class MlApiClient:
    ROUTES = {"status": "/v1/status", "evaluations": "/v1/evaluations", "predictions": "/v1/predictions", "infer": "/v1/infer"}

    def __init__(self, base_url=None, timeout=2):
        if base_url:
            parsed = urlsplit(base_url)
            if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
                raise ValueError("API ML exige URL HTTP de serviço, sem credenciais ou caminho.")
        self.base_url, self.timeout = base_url.rstrip("/") if base_url else None, timeout

    def request(self, route, payload=None):
        if route not in self.ROUTES:
            return 404, {"error": "not_found"}
        if not self.base_url:
            return 503, {"schema_version": 1, "status": "unavailable", "error": "ml_service_not_configured", "metrics": None}
        try:
            data = json.dumps(payload, allow_nan=False).encode() if payload is not None else None
            request = Request(self.base_url + self.ROUTES[route], data, {"Content-Type": "application/json"})
            try:
                response = urlopen(request, timeout=self.timeout)
            except HTTPError as exc:
                response = exc
            with response:
                body = response.read(2 * 1024 * 1024 + 1)
                if len(body) > 2 * 1024 * 1024:
                    raise ValueError("Resposta ML excede o limite.")
                return response.status, json.loads(body)
        except (OSError, URLError, ValueError, TypeError):
            return 503, {"schema_version": 1, "status": "unavailable", "error": "ml_service_unavailable", "metrics": None}
