"""Isolated RFC 3161 Time-Stamping Authority test double (tests only).

Creates a throw-away CA and TSA certificate in a temp directory and signs real RFC 3161 responses with
``openssl ts -reply``. It is never configured as a trusted provider outside tests: its CA exists only in
the pytest temp directory.
"""

from __future__ import annotations

import datetime as dt
import subprocess
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


@dataclass
class TestTsa:
    dir: Path
    ca_pem: Path
    tsa_pem: Path
    tsa_key: Path
    config: Path

    def reply(self, tsq_der: bytes) -> bytes:
        q = self.dir / "req.tsq"
        r = self.dir / "resp.tsr"
        q.write_bytes(tsq_der)
        subprocess.run(
            ["openssl", "ts", "-reply", "-config", str(self.config), "-queryfile", str(q),
             "-signer", str(self.tsa_pem), "-inkey", str(self.tsa_key), "-chain", str(self.ca_pem), "-out", str(r)],
            check=True, capture_output=True,
        )
        return r.read_bytes()


def _name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn), x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SAHAKAR test only")])


def make_tsa(directory: Path, label: str = "Test") -> TestTsa:
    directory.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_cert = (
        x509.CertificateBuilder().subject_name(_name(f"{label} Root CA")).issuer_name(_name(f"{label} Root CA"))
        .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now).not_valid_after(now + dt.timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                                     data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                                     encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    tsa_key = ec.generate_private_key(ec.SECP256R1())
    tsa_cert = (
        x509.CertificateBuilder().subject_name(_name(f"{label} TSA")).issuer_name(ca_cert.subject)
        .public_key(tsa_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now).not_valid_after(now + dt.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_encipherment=False,
                                     data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                                     encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    pem = serialization.Encoding.PEM
    ca_pem, tsa_pem, key = directory / "ca.pem", directory / "tsa.pem", directory / "tsa.key"
    ca_pem.write_bytes(ca_cert.public_bytes(pem))
    tsa_pem.write_bytes(tsa_cert.public_bytes(pem))
    key.write_bytes(tsa_key.private_bytes(pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    serial = directory / "serial"
    serial.write_text("01\n")
    config = directory / "tsa.cnf"
    config.write_text(
        "[ tsa ]\ndefault_tsa = tsa_config1\n[ tsa_config1 ]\n"
        f"serial = {serial}\ncrypto_device = builtin\nsigner_digest = sha256\ndefault_policy = 1.3.6.1.4.1.99999.1\n"
        "other_policies = 1.3.6.1.4.1.99999.2\ndigests = sha256\naccuracy = secs:1\nordering = no\ntsa_name = no\n"
        "ess_cert_id_chain = no\ness_cert_id_alg = sha256\n"
    )
    return TestTsa(directory, ca_pem, tsa_pem, key, config)
