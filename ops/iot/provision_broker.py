"""Prepara certificados e contas do Mosquitto local sem exibir senhas.

Não inicia serviços, acessa a placa, modifica firewall ou edita o header do firmware.
O diretório de destino deve ser novo; se já existir, nada será sobrescrito.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import subprocess

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


IMAGE = "eclipse-mosquitto:2.0.22@sha256:81a6193ae693942a3231cd3ac52875b02b7e3a19da671b2fb4b55cc874c5b279"
ROOT = Path(__file__).resolve().parents[2]


def docker_command():
    return ["wsl", "-d", "Ubuntu", "--", "docker"] if os.name == "nt" else ["docker"]


def docker_run(args, *, input_text=None):
    # Não propagar saída do mosquitto_passwd, prompts ou dados de entrada ao log.
    result = subprocess.run(docker_command() + args, input=input_text, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if result.returncode:
        raise RuntimeError("Falha ao executar Docker/Mosquitto; nenhum segredo foi exibido.")


def secure_directory(folder):
    folder.mkdir(mode=0o700)  # Falha se já existe: não substitui credenciais anteriores.
    if os.name == "nt":
        row = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], text=True)
        sid = next(csv.reader([row.strip()]))[1]
        result = subprocess.run(
            ["icacls", str(folder), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F",
             "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F"],
            capture_output=True, text=True,
        )
        if result.returncode:
            raise RuntimeError("Não foi possível restringir a ACL da pasta; nenhum segredo foi gerado.")
    else:
        folder.chmod(0o700)


def build_certificates(folder, server_ip):
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MotionLab Local CA")])
    server_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, str(server_ip))])
    ca_ski = x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key())
    issuer_aki = x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(ca_ski)
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=365))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                                       key_encipherment=False, data_encipherment=False,
                                       key_agreement=False, key_cert_sign=True, crl_sign=True,
                                       encipher_only=False, decipher_only=False), critical=True)
          .add_extension(ca_ski, critical=False)
          .add_extension(issuer_aki, critical=False)
          .sign(ca_key, hashes.SHA256()))
    cert = (x509.CertificateBuilder().subject_name(server_name).issuer_name(ca_name)
            .public_key(server_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=90))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            # mbedTLS 2.28.7 (ESP-IDF 4.4) only matches dNSName SANs against
            # its textual hostname; modern clients still need the IPAddress SAN.
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(server_ip),
                                                        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                                                        x509.DNSName(str(server_ip))]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()), critical=False)
            .add_extension(issuer_aki, critical=False)
            .sign(ca_key, hashes.SHA256()))
    for name, key in (("ca.key", ca_key), ("server.key", server_key)):
        (folder / name).write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                                       serialization.PrivateFormat.PKCS8,
                                                       serialization.NoEncryption()))
        if os.name != "nt":
            (folder / name).chmod(0o600)
    (folder / "ca.crt").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (folder / "server.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def provision(folder, server_ip, device_id):
    if os.name != "nt":
        raise RuntimeError("O provisionador requer Windows com Docker no WSL.")
    if (not isinstance(server_ip, ipaddress.IPv4Address) or not server_ip.is_private
            or server_ip.is_loopback or server_ip.is_unspecified or server_ip.is_link_local):
        raise ValueError("Informe o IPv4 privado do Windows na LAN, sem usar loopback.")
    if not re.fullmatch(r"esp32_[0-9a-f]{12}", device_id):
        raise ValueError("O device_id deve ser esp32_ seguido de 12 dígitos hexadecimais minúsculos.")
    if folder.exists():
        raise FileExistsError("A pasta de destino já existe; nenhum arquivo será sobrescrito.")
    docker_run(["image", "inspect", IMAGE])
    secure_directory(folder)
    build_certificates(folder, server_ip)
    device_secret, ingest_secret = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    if os.name == "nt":
        volume = subprocess.check_output(["wsl", "-d", "Ubuntu", "--", "wslpath", "-a", "-u",
                                          str(folder).replace("\\", "/")], text=True).strip()
    else:
        volume = str(folder.resolve())
    for username, secret, create in ((device_id, device_secret, True), ("motionlab_ingest", ingest_secret, False)):
        args = ["run", "--pull=never", "--rm", "-i", "--network", "none", "--user", "0:0",
                "-v", f"{volume}:/local", IMAGE, "mosquitto_passwd"]
        if create:
            args.append("-c")
        args += ["/local/passwords", username]
        docker_run(args, input_text=f"{secret}\n{secret}\n")
    credentials = {"device_id": device_id, "device_password": device_secret,
                   "ingest_username": "motionlab_ingest", "ingest_password": ingest_secret,
                   "server_ip": str(server_ip)}
    (folder / "credentials.json").write_text(json.dumps(credentials, indent=2) + "\n", encoding="utf-8")
    if os.name != "nt":
        (folder / "credentials.json").chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-ip", type=ipaddress.ip_address, required=True)
    parser.add_argument("--device-id", required=True)
    args = parser.parse_args()
    try:
        provision(ROOT / "ops/iot/local", args.server_ip, args.device_id)
    except (ValueError, FileExistsError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Provisionamento interrompido: {exc}\n")
    print("Certificados e contas gerados na pasta privada ops/iot/local. Nenhum serviço foi iniciado.")


if __name__ == "__main__":
    main()
