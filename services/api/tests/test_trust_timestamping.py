"""RFC 3161 verification tests against an isolated local test TSA (no network, no database).

A real signed token from the test TSA verifies only when *its* CA is the pinned trust anchor. Everything
else (another CA, a forged signature, a different digest, a wrong nonce, junk bytes, HTTP 200 with a
non-timestamp body) is rejected.
"""

import httpx
import pytest

from app.trust import crypto, timestamping
from tsa_double import make_tsa


@pytest.fixture(scope="module")
def tsa(tmp_path_factory):
    return make_tsa(tmp_path_factory.mktemp("tsa"), "Test")


@pytest.fixture(scope="module")
def other_ca(tmp_path_factory):
    return make_tsa(tmp_path_factory.mktemp("other"), "Other")


def _signed(tsa, digest_hex):
    req = timestamping.build_request(digest_hex)
    return req, tsa.reply(req.der)


def test_genuine_token_verifies_against_pinned_anchor(tsa) -> None:
    digest = crypto.sha256_hex(b"checkpoint")
    req, der = _signed(tsa, digest)
    v = timestamping.verify_response(der, digest, str(tsa.ca_pem), req.nonce)
    assert v.hash_algorithm == "sha256" and v.nonce == req.nonce
    assert "Test TSA" in v.signer_subject


def test_token_rejected_under_a_different_trust_anchor(tsa, other_ca) -> None:
    digest = crypto.sha256_hex(b"checkpoint")
    req, der = _signed(tsa, digest)
    # The response carries the signer and CA certificates, but they are never trusted on their own.
    with pytest.raises(timestamping.TimestampVerificationError, match="certificate|signature"):
        timestamping.verify_response(der, digest, str(other_ca.ca_pem), req.nonce)


def test_digest_mismatch_and_nonce_mismatch_rejected(tsa) -> None:
    digest = crypto.sha256_hex(b"checkpoint")
    req, der = _signed(tsa, digest)
    with pytest.raises(timestamping.TimestampVerificationError, match="imprint"):
        timestamping.verify_response(der, crypto.sha256_hex(b"other"), str(tsa.ca_pem), req.nonce)
    with pytest.raises(timestamping.TimestampVerificationError, match="nonce"):
        timestamping.verify_response(der, digest, str(tsa.ca_pem), req.nonce + 1)


def test_forged_signature_rejected(tsa) -> None:
    digest = crypto.sha256_hex(b"checkpoint")
    req, der = _signed(tsa, digest)
    forged = bytearray(der)
    forged[-5] ^= 0xFF  # inside the CMS signature value
    with pytest.raises(timestamping.TimestampVerificationError):
        timestamping.verify_response(bytes(forged), digest, str(tsa.ca_pem), req.nonce)


@pytest.mark.parametrize("junk", [b"", b"OK", b"<html>200 OK</html>", bytes(64)])
def test_unsigned_or_junk_evidence_rejected(tsa, junk) -> None:
    with pytest.raises(timestamping.TimestampVerificationError):
        timestamping.verify_response(junk, crypto.sha256_hex(b"x"), str(tsa.ca_pem))


def test_missing_trust_anchor_is_never_treated_as_valid(tsa) -> None:
    digest = crypto.sha256_hex(b"checkpoint")
    req, der = _signed(tsa, digest)
    with pytest.raises(timestamping.TimestampVerificationError, match="trust anchor"):
        timestamping.verify_response(der, digest, "", req.nonce)


def test_http_200_with_wrong_content_type_is_not_evidence(monkeypatch) -> None:
    def fake_post(url, content, headers, timeout):
        return httpx.Response(200, content=b"granted!", headers={"content-type": "text/html"})

    monkeypatch.setattr(timestamping.httpx, "post", fake_post)
    with pytest.raises(timestamping.TimestampError, match="content type"):
        timestamping.submit("http://tsa.invalid/", timestamping.build_request(crypto.sha256_hex(b"x")))


def test_unreachable_tsa_raises_timestamp_error(monkeypatch) -> None:
    def boom(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(timestamping.httpx, "post", boom)
    with pytest.raises(timestamping.TimestampError, match="unreachable"):
        timestamping.submit("http://tsa.invalid/", timestamping.build_request(crypto.sha256_hex(b"x")))


def test_request_contains_only_the_digest_and_nonce() -> None:
    from asn1crypto import tsp

    digest = crypto.sha256_hex(b"checkpoint")
    req = timestamping.build_request(digest)
    parsed = tsp.TimeStampReq.load(req.der).native
    assert parsed["message_imprint"]["hashed_message"] == bytes.fromhex(digest)
    assert parsed["message_imprint"]["hash_algorithm"]["algorithm"] == "sha256"
    assert set(k for k, v in parsed.items() if v is not None) <= {"version", "message_imprint", "nonce", "cert_req"}
