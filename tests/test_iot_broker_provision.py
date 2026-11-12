import ipaddress
import socket
import ssl
import threading

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from ops.iot import provision_broker


def test_certificates_are_signed_and_include_both_required_ips(tmp_path):
    ip = ipaddress.ip_address("192.168.15.14")
    provision_broker.build_certificates(tmp_path, ip)
    ca = x509.load_pem_x509_certificate((tmp_path / "ca.crt").read_bytes())
    cert = x509.load_pem_x509_certificate((tmp_path / "server.crt").read_bytes())
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert names.get_values_for_type(x509.IPAddress) == [ip, ipaddress.ip_address("127.0.0.1")]
    # ESP-IDF 4.4's mbedTLS 2.28.7 matches DNS SANs but not IP SANs.
    assert names.get_values_for_type(x509.DNSName) == [str(ip)]
    assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    ca_ski = ca.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest
    assert ca.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value.key_identifier == ca_ski
    assert cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value.key_identifier == ca_ski
    assert cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest
    ca.public_key().verify(cert.signature, cert.tbs_certificate_bytes, padding.PKCS1v15(), hashes.SHA256())


def test_tls_handshake_succeeds_with_python_default_strict_verification(tmp_path):
    provision_broker.build_certificates(tmp_path, ipaddress.ip_address("192.168.15.14"))
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(tmp_path / "server.crt", tmp_path / "server.key")
    client_context = ssl.create_default_context(cafile=str(tmp_path / "ca.crt"))
    client_context.verify_flags |= ssl.VERIFY_X509_STRICT
    server_socket, client_socket = socket.socketpair()
    server_socket.settimeout(5)
    client_socket.settimeout(5)
    errors = []

    def serve():
        try:
            with server_context.wrap_socket(server_socket, server_side=True) as connection:
                connection.sendall(connection.recv(4))
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=serve)
    thread.start()
    try:
        with client_context.wrap_socket(client_socket, server_hostname="192.168.15.14") as connection:
            connection.sendall(b"ping")
            assert connection.recv(4) == b"ping"
    finally:
        client_socket.close()
        thread.join(timeout=6)
    assert not thread.is_alive()
    assert not errors


def test_existing_directory_is_never_overwritten(tmp_path, monkeypatch):
    if provision_broker.os.name != "nt":
        pytest.skip("Provisionamento da bancada é específico do Windows/WSL.")
    sentinel = tmp_path / "do-not-overwrite"
    sentinel.write_text("preserve", encoding="utf-8")
    monkeypatch.setattr(provision_broker, "docker_run", lambda *args, **kwargs: pytest.fail("não chamar Docker"))
    with pytest.raises(FileExistsError):
        provision_broker.provision(tmp_path, ipaddress.ip_address("192.168.15.14"), "esp32_20500d17d774")
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_invalid_device_id_is_rejected_before_creating_directory(tmp_path):
    if provision_broker.os.name != "nt":
        pytest.skip("Provisionamento da bancada é específico do Windows/WSL.")
    target = tmp_path / "new"
    with pytest.raises(ValueError):
        provision_broker.provision(target, ipaddress.ip_address("192.168.15.14"), "esp32_INVALID")
    assert not target.exists()
