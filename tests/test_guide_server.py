"""HTTP local real; somente a USB fisica e suas leituras sao substituidas nos testes."""
import json
import re
import threading
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from terminal.bench import guide


def request_data(component="lcd", *, complete=False):
    return {"component": component, "port": "COM7", "measurements": {
        "supply_3v3": 3.30 if complete else None,
        "echo_v": 2.83 if complete else None,
        "reference_cm": 25.0 if complete else None,
    }, "confirmations": {"wiring": complete, "lcd_visual": complete}}


def snapshot(**overrides):
    data = dict(origin="ESP32_HW", is_physical_hardware=True, sample_period_ms=70,
                free_heap_bytes=100000, fw_version="0.5.0-cycle5")
    data.update(overrides)
    return SimpleNamespace(**data, to_dict=lambda: dict(data))


def stream(**overrides):
    data = dict(sensor_frames_count=30, parse_errors=0, seq_gaps_detected=0,
                period_within_tolerance=True, valid_ultrasonic_count=30,
                timeout_ratio=0.0, reference_within_tolerance=True,
                lcd_frames_count=3, last_lcd_lines=tuple("line".ljust(20) for _ in range(4)),
                ir_true_count=15, ir_false_count=15, ir_transitions=2)
    data.update(overrides)
    return SimpleNamespace(**data, to_dict=lambda: dict(data))


@pytest.fixture
def physical(monkeypatch):
    endpoints = []

    class FakeEndpoint:
        def __init__(self, port, baudrate=115200):
            assert port == "COM7" and baudrate == 115200
            self.commands = []
            self.closed = False
            endpoints.append(self)

        def write_line(self, line):
            self.commands.append(line)

        def close(self):
            self.closed = True

    monkeypatch.setattr(guide, "list_serial_ports", lambda: [SimpleNamespace(device="COM7", description="USB ESP32")])
    monkeypatch.setattr(guide, "PySerialEndpoint", FakeEndpoint)
    monkeypatch.setattr(guide, "query_device_diag", lambda *args, **kwargs: snapshot())
    monkeypatch.setattr(guide, "inspect_telemetry_stream", lambda *args, **kwargs: stream())
    return endpoints


def test_esp32_only_ignores_expected_ultrasonic_timeouts(physical, monkeypatch, tmp_path):
    monkeypatch.setattr(guide, "inspect_telemetry_stream", lambda *args, **kwargs:
                        stream(valid_ultrasonic_count=0, timeout_ratio=1.0))
    result = guide.run_physical_test(request_data("esp32"), tmp_path / "log.json")
    assert result["status"] == "passed"
    assert result["details"]["captured"] and not result["details"]["ultrasonic_required"]
    assert physical[0].closed
    assert physical[0].commands == ["START"]


@pytest.mark.parametrize("component", ["lcd", "ir"])
def test_lcd_and_ir_can_observe_without_measurements_but_remain_pending(physical, monkeypatch, tmp_path, component):
    monkeypatch.setattr(guide, "inspect_telemetry_stream", lambda *args, **kwargs:
                        stream(valid_ultrasonic_count=0, timeout_ratio=1.0))
    result = guide.run_physical_test(request_data(component), tmp_path / "log.json")
    assert result["status"] == "pending"
    assert result["details"]["captured"]
    assert result["details"]["automatic_voltage_measurement"] is False
    assert len(result["details"]["device_lcd_20x4"]) == 4
    assert physical[0].closed


@pytest.mark.parametrize("component", ["lcd", "ir", "hcsr04", "all"])
def test_component_passes_only_with_required_capture_and_manual_evidence(physical, tmp_path, component):
    result = guide.run_physical_test(request_data(component, complete=True), tmp_path / "log.json")
    assert result["status"] == "passed"
    history = json.loads((tmp_path / "log.json").read_text(encoding="utf-8"))
    assert history[-1]["passed"]
    assert history[-1]["payload"]["details"]["operator_confirmations"]["wiring"]
    assert result["details"]["echo_measurement_kind"] == "operator_static_divider_test_not_echo_peak"


def test_lcd_frame_without_visual_confirmation_stays_pending(physical, tmp_path):
    data = request_data(complete=True)
    data["confirmations"]["lcd_visual"] = False
    result = guide.run_physical_test(data, tmp_path / "log.json")
    assert result["status"] == "pending"
    assert any("LCD fisico" in p for p in result["problems"])


@pytest.mark.parametrize("component,patch", [("lcd", {"lcd_frames_count": 0, "last_lcd_lines": ()}),
    ("ir", {"ir_transitions": 0, "ir_false_count": 0}), ("hcsr04", {"reference_within_tolerance": False}),
    ("hcsr04", {"valid_ultrasonic_count": 0, "timeout_ratio": 1.0}),
    ("esp32", {"sensor_frames_count": 2}), ("esp32", {"parse_errors": 2})])
def test_missing_device_evidence_cannot_be_approved(physical, monkeypatch, tmp_path, component, patch):
    monkeypatch.setattr(guide, "inspect_telemetry_stream", lambda *args, **kwargs: stream(**patch))
    result = guide.run_physical_test(request_data(component, complete=True), tmp_path / "log.json")
    assert result["status"] == "failed" and result["problems"]


@pytest.mark.parametrize("field,value", [("echo_v", None), ("reference_cm", None), ("echo_v", 3.5), ("echo_v", 2.0), ("reference_cm", 500.0)])
def test_hcsr_missing_or_unsafe_preflight_never_opens_usb(physical, tmp_path, field, value):
    data = request_data("hcsr04", complete=True)
    data["measurements"][field] = value
    result = guide.run_physical_test(data, tmp_path / "log.json")
    assert result["status"] == ("pending" if value is None else "failed")
    assert not physical and not result["details"]["captured"]


def test_5v_on_direct_lcd_prevents_usb_capture(physical, tmp_path):
    data = request_data(complete=True)
    data["measurements"]["supply_3v3"] = 5.0
    assert guide.run_physical_test(data, tmp_path / "log.json")["status"] == "failed"
    assert not physical


def test_simulator_origin_cannot_pass_as_physical_esp32(physical, monkeypatch, tmp_path):
    monkeypatch.setattr(guide, "query_device_diag", lambda *args, **kwargs:
                        snapshot(origin="SIMULATOR", is_physical_hardware=False))
    result = guide.run_physical_test(request_data("esp32"), tmp_path / "log.json")
    assert result["status"] == "failed" and not result["details"]["captured"]
    assert physical[0].closed and not physical[0].commands


def test_serial_busy_is_a_readable_failure(physical, monkeypatch, tmp_path):
    def busy(*args, **kwargs):
        raise OSError("Porta ocupada")
    monkeypatch.setattr(guide, "PySerialEndpoint", busy)
    result = guide.run_physical_test(request_data("esp32"), tmp_path / "log.json")
    assert result["status"] == "failed"
    assert "Porta ocupada" in result["problems"][0]


def test_diag_retry_supports_boot_and_releases_serial(physical, monkeypatch, tmp_path):
    timeouts = []
    def diag(*args, **kwargs):
        timeouts.append(kwargs["timeout_sec"])
        if len(timeouts) == 1:
            raise TimeoutError("boot")
        return snapshot()
    monkeypatch.setattr(guide, "query_device_diag", diag)
    result = guide.run_physical_test(request_data("esp32"), tmp_path / "log.json")
    assert result["status"] == "passed" and timeouts == [4.0, 3.0]
    assert physical[0].closed


@pytest.mark.parametrize("value", [True, "3.3", float("nan"), float("inf"), 10 ** 1000])
def test_request_measurements_must_be_finite_numbers(value):
    data = request_data()
    data["measurements"]["supply_3v3"] = value
    with pytest.raises(guide.RequestError):
        guide.validate_request(data)


@pytest.fixture
def http_service(physical, tmp_path):
    server = guide.GuideServer(port=0, log_path=tmp_path / "log.json")
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    worker.start()
    yield server
    server.shutdown()
    server.server_close()
    worker.join(timeout=2)


def http_call(server, path, data=None, *, method=None, headers=None, key=True, raw=None):
    options = {"X-MotionPet-Key": server.api_key} if key else {}
    if data is not None or raw is not None:
        options["Content-Type"] = "application/json"
    options.update(headers or {})
    body = raw if raw is not None else json.dumps(data).encode("utf-8") if data is not None else None
    request = Request(server.origin + path, data=body, headers=options, method=method)
    try:
        response = urlopen(request, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        text = response.read().decode("utf-8")
        return response.status, json.loads(text) if response.headers.get_content_type() == "application/json" else text


def test_http_serves_actual_guide_with_runtime_key_and_lists_ports(http_service):
    status, page = http_call(http_service, "/", key=False)
    assert status == 200
    assert re.search(r'<meta name="motionpet-key" content="' + re.escape(http_service.api_key) + r'">', page)
    assert "Montagem" in page or "montagem" in page
    status, ports = http_call(http_service, "/api/ports")
    assert status == 200 and ports == {"ports": [{"device": "COM7", "description": "USB ESP32"}]}


def test_http_reads_current_generated_guide_without_caching_old_steps(http_service, monkeypatch, tmp_path):
    page = tmp_path / "guide.html"
    monkeypatch.setattr(guide, "GUIDE_HTML_PATH", page)
    page.write_text('<html><head></head><body>primeira versao</body></html>', encoding='utf-8')
    assert 'primeira versao' in http_call(http_service, '/', key=False)[1]
    page.write_text('<html><head></head><body>versao corrigida dos fios</body></html>', encoding='utf-8')
    status, content = http_call(http_service, '/', key=False)
    assert status == 200 and 'versao corrigida dos fios' in content
    assert 'primeira versao' not in content
    assert http_service.api_key in content


def test_http_reports_missing_generated_guide(http_service, monkeypatch, tmp_path):
    monkeypatch.setattr(guide, 'GUIDE_HTML_PATH', tmp_path / 'missing.html')
    status, data = http_call(http_service, '/', key=False)
    assert status == 503 and 'Gere os arquivos' in data['error']


def test_http_runs_physical_component_contract(http_service):
    status, result = http_call(http_service, "/api/test", request_data("esp32"))
    assert status == 200 and result["status"] == "passed"
    assert result["validation_origin"] == "PHYSICAL_ESP32"
    assert result["details"]["captured"]


@pytest.mark.parametrize("headers,key", [({}, False), ({"X-MotionPet-Key": "wrong"}, True),
    ({"X-MotionPet-Key": "inválido"}, True), ({"Host": "attacker.example"}, True),
    ({"Origin": "https://attacker.example"}, True)])
def test_http_denies_missing_key_external_origin_and_dns_rebinding(http_service, headers, key):
    status, result = http_call(http_service, "/api/ports", headers=headers, key=key)
    assert status == 403 and "error" in result


@pytest.mark.parametrize("path", ["/.env", "/firmware/main/main.cpp", "/../pyproject.toml", "/docs/../../.env", "/api/flash"])
def test_http_cannot_read_arbitrary_files_or_flash_firmware(http_service, path):
    assert http_call(http_service, path)[0] == 404


@pytest.mark.parametrize("patch", [{"simulate": True}, {"port": "COM999"}, {"component": "flash"}, {"confirmations": {"wiring": "yes"}}, {"measurements": {"supply_3v3": True}}])
def test_http_rejects_invalid_actions_ports_and_coerced_measurements(http_service, physical, patch):
    data = request_data("esp32")
    data.update(patch)
    status, result = http_call(http_service, "/api/test", data)
    assert status == 400 and "error" in result
    assert not physical


def test_http_only_one_capture_can_own_usb(http_service, physical):
    http_service.capture_lock.acquire()
    try:
        status, result = http_call(http_service, "/api/test", request_data("esp32"))
        assert status == 409 and "andamento" in result["error"]
        assert not physical
    finally:
        http_service.capture_lock.release()


@pytest.mark.parametrize("raw", [b"[]", b"not-json", b'{"component":"lcd","port":"COM7","measurements":{"echo_v":NaN}}', b"x" * (guide.MAX_BODY_BYTES + 1)])
def test_http_rejects_malformed_or_oversized_bodies(http_service, physical, raw):
    status, result = http_call(http_service, "/api/test", raw=raw, method="POST")
    assert status in (400, 413) and "error" in result
    assert not physical


def test_http_does_not_enable_cross_origin_preflight(http_service):
    assert http_call(http_service, "/api/test", method="OPTIONS")[0] == 403
