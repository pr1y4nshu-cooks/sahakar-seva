"""RFC 3161 Time-Stamp Protocol client and verifier.

Mature implementations do the hard parts:
- ``asn1crypto`` builds the TimeStampReq and parses the TimeStampResp / TSTInfo (no hand-written ASN.1);
- the OpenSSL ``ts -verify`` command performs the CMS signature check, certificate-chain validation
  against a *pinned* trust anchor file, the timeStamping extended-key-usage check on the signer, the
  ESS signing-certificate binding and the message-imprint comparison.

We add explicit, independent checks on top (granted status, SHA-256 imprint equality, nonce equality,
signer EKU critical + timeStamping, signer validity at genTime). Certificates embedded in the response
are only ever used as untrusted chain-building material; the trust anchor always comes from
configuration (``TSA_CA_FILE``) and is never taken from the response.

Limitations (documented): revocation (CRL/OCSP) is not checked; the chain is validated at the token's
genTime (``-attime``) so an archived token stays verifiable after the TSA certificate expires.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from asn1crypto import algos, cms, tsp, x509

TSQ_CONTENT_TYPE = "application/timestamp-query"
TSR_CONTENT_TYPE = "application/timestamp-reply"


class TimestampError(Exception):
    """The TSA could not be reached or answered with something that is not usable evidence."""


class TimestampVerificationError(TimestampError):
    """A response was received but failed cryptographic or semantic verification."""


@dataclass(frozen=True)
class TimestampRequest:
    der: bytes
    nonce: int
    digest_hex: str


@dataclass(frozen=True)
class VerifiedTimestamp:
    gen_time: datetime
    serial_number: str
    policy_oid: str
    signer_subject: str
    hash_algorithm: str
    nonce: int | None


def build_request(digest_hex: str, nonce: int | None = None) -> TimestampRequest:
    digest = bytes.fromhex(digest_hex)
    if len(digest) != 32:
        raise ValueError("only SHA-256 digests are timestamped")
    nonce = nonce if nonce is not None else secrets.randbits(63)
    req = tsp.TimeStampReq(
        {
            "version": "v1",
            "message_imprint": tsp.MessageImprint(
                {"hash_algorithm": algos.DigestAlgorithm({"algorithm": "sha256"}), "hashed_message": digest}
            ),
            "nonce": nonce,
            "cert_req": True,
        }
    )
    return TimestampRequest(der=req.dump(), nonce=nonce, digest_hex=digest_hex)


def submit(url: str, request: TimestampRequest, timeout_s: float = 15.0) -> bytes:
    """POST the request. Only the 32-byte digest and a random nonce leave the system."""
    try:
        response = httpx.post(
            url, content=request.der, headers={"Content-Type": TSQ_CONTENT_TYPE}, timeout=timeout_s
        )
    except httpx.HTTPError as exc:
        raise TimestampError(f"TSA unreachable: {type(exc).__name__}") from exc
    if response.status_code != 200:
        raise TimestampError(f"TSA answered HTTP {response.status_code}")
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type != TSR_CONTENT_TYPE:
        raise TimestampError(f"TSA answered with content type '{content_type or 'none'}', not a timestamp reply")
    if not response.content:
        raise TimestampError("TSA answered with an empty body")
    return response.content


def _openssl() -> str:
    path = os.environ.get("OPENSSL_BIN") or shutil.which("openssl")
    if not path:
        raise TimestampVerificationError("OpenSSL command-line tool not found; cannot verify timestamp signatures")
    return path


def _signer_certificate(signed_data: cms.SignedData) -> x509.Certificate:
    infos = signed_data["signer_infos"]
    if len(infos) != 1:
        raise TimestampVerificationError("timestamp token must have exactly one signer")
    sid = infos[0]["sid"]
    for choice in signed_data["certificates"] or []:
        if choice.name != "certificate":
            continue
        cert = choice.chosen
        if sid.name == "issuer_and_serial_number":
            ias = sid.chosen
            if cert.issuer == ias["issuer"] and cert.serial_number == ias["serial_number"].native:
                return cert
        elif sid.name == "subject_key_identifier" and cert.key_identifier == sid.chosen.native:
            return cert
    raise TimestampVerificationError("signer certificate not present in the token (cert_req was set)")


def parse_response(tsr_der: bytes) -> tuple[tsp.TimeStampResp, cms.SignedData, tsp.TSTInfo]:
    try:
        resp = tsp.TimeStampResp.load(tsr_der)
        status = resp["status"]["status"].native
    except Exception as exc:  # malformed DER
        raise TimestampVerificationError("response is not a valid RFC 3161 TimeStampResp") from exc
    if status not in ("granted", "granted_with_mods"):
        raise TimestampVerificationError(f"TSA did not grant the timestamp (status '{status}')")
    try:
        token = resp["time_stamp_token"]
        if token["content_type"].native != "signed_data":
            raise TimestampVerificationError("timestamp token is not CMS SignedData")
        signed_data = token["content"]
        encap = signed_data["encap_content_info"]
        if encap["content_type"].native != "tst_info":
            raise TimestampVerificationError("token does not encapsulate a TSTInfo")
        tst_info = encap["content"].parsed
        _ = tst_info["gen_time"].native
    except TimestampVerificationError:
        raise
    except Exception as exc:
        raise TimestampVerificationError("timestamp token could not be parsed") from exc
    return resp, signed_data, tst_info


def verify_response(
    tsr_der: bytes,
    expected_digest_hex: str,
    ca_file: str,
    expected_nonce: int | None = None,
) -> VerifiedTimestamp:
    """Fully verify a TimeStampResp against the pinned trust anchor in ``ca_file``.

    Raises TimestampVerificationError on any failure. A successful return is the only path to the
    EXTERNALLY_ANCHORED status.
    """
    if not ca_file or not os.path.isfile(ca_file):
        raise TimestampVerificationError("no pinned TSA trust anchor file is configured")
    _resp, signed_data, tst_info = parse_response(tsr_der)

    imprint = tst_info["message_imprint"]
    alg = imprint["hash_algorithm"]["algorithm"].native
    if alg != "sha256":
        raise TimestampVerificationError(f"unsupported imprint hash algorithm '{alg}'")
    if imprint["hashed_message"].native != bytes.fromhex(expected_digest_hex):
        raise TimestampVerificationError("message imprint does not match the checkpoint digest")
    token_nonce = tst_info["nonce"].native
    if expected_nonce is not None and token_nonce != expected_nonce:
        raise TimestampVerificationError("nonce in the token does not match the request nonce")

    gen_time: datetime = tst_info["gen_time"].native
    if gen_time.tzinfo is None:
        gen_time = gen_time.replace(tzinfo=timezone.utc)

    signer = _signer_certificate(signed_data)
    eku = signer.extended_key_usage_value
    if eku is None or "time_stamping" not in eku.native:
        raise TimestampVerificationError("signer certificate lacks the timeStamping extended key usage")
    eku_critical = any(
        ext["extn_id"].native == "extended_key_usage" and ext["critical"].native
        for ext in signer["tbs_certificate"]["extensions"]
    )
    if not eku_critical:
        raise TimestampVerificationError("signer timeStamping extended key usage must be critical (RFC 3161 §2.3)")
    validity = signer["tbs_certificate"]["validity"]
    if not validity["not_before"].native <= gen_time <= validity["not_after"].native:
        raise TimestampVerificationError("signer certificate was not valid at the timestamp time")

    # Cryptographic verification by OpenSSL against the pinned anchor, evaluated at genTime.
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "response.tsr")
        with open(path, "wb") as fh:
            fh.write(tsr_der)
        cmd = [
            _openssl(), "ts", "-verify",
            "-digest", expected_digest_hex,
            "-in", path,
            "-CAfile", ca_file,
            "-attime", str(int(gen_time.timestamp())),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0 or "Verification: OK" not in output:
            reason = output.splitlines()[-1] if output else "unknown error"
            raise TimestampVerificationError(f"signature/certificate-chain verification failed: {reason[:300]}")

    return VerifiedTimestamp(
        gen_time=gen_time.astimezone(timezone.utc),
        serial_number=str(tst_info["serial_number"].native),
        policy_oid=tst_info["policy"].dotted,
        signer_subject=signer.subject.human_friendly,
        hash_algorithm=alg,
        nonce=token_nonce,
    )


def ca_fingerprint(ca_file: str) -> str | None:
    """SHA-256 fingerprint of the first certificate in a PEM file (for display and pinning docs)."""
    try:
        with open(ca_file, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    from asn1crypto import pem

    if pem.detect(data):
        _, _, data = pem.unarmor(data)
    return hashlib.sha256(data).hexdigest()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
