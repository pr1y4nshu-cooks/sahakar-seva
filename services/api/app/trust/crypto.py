"""Deterministic serialization, hashing and Merkle trees for financial evidence (format v1).

Byte-level definitions (documented in docs/architecture/FINANCIAL_TRANSPARENCY_AND_ANCHORING.md §4):

    canonical(x)   = RFC 8785 JSON Canonicalization Scheme (JCS) bytes, via the ``rfc8785`` package.
                     Profile restriction: no floats, integers within +/- (2**53 - 1), ASCII object keys.
    payload_hash   = SHA-256( PAYLOAD_DOMAIN || canonical(payload) )
    event_hash     = SHA-256( EVENT_DOMAIN || uint64_be(sequence) || prev_event_hash[32] || payload_hash[32] )
    genesis prev   = 32 zero bytes
    merkle leaf    = SHA-256( 0x00 || event_hash[32] )                       (RFC 9162 §2.1.1)
    merkle node    = SHA-256( 0x01 || left[32] || right[32] )
    checkpoint     = SHA-256( CHECKPOINT_DOMAIN || canonical(checkpoint_body) )

Every variable-length input is the last field of its hash (or is a fixed 32-byte digest), and each hash
has its own NUL-terminated domain separator, so no two different inputs share a byte encoding.
"""

from __future__ import annotations

import hashlib
from typing import Any

import rfc8785

HASH_ALG = "sha-256"
EVENT_FORMAT = "sahakar-seva/financial-event/v1"
CHECKPOINT_FORMAT = "sahakar-seva/checkpoint/v1"
RECEIPT_FORMAT = "sahakar-seva/receipt/v1"

PAYLOAD_DOMAIN = b"SAHAKAR-SEVA:financial-event-payload:v1\x00"
EVENT_DOMAIN = b"SAHAKAR-SEVA:financial-event:v1\x00"
CHECKPOINT_DOMAIN = b"SAHAKAR-SEVA:checkpoint:v1\x00"
GENESIS_HASH = "00" * 32

MAX_SAFE_INT = 2**53 - 1


class CanonicalizationError(ValueError):
    pass


def _check_profile(value: Any, path: str = "$") -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INT:
            raise CanonicalizationError(f"{path}: integer outside the interoperable range")
        return
    if isinstance(value, float):
        raise CanonicalizationError(f"{path}: floats are not allowed in committed payloads (use integer paise)")
    if isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            _check_profile(item, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key.isascii():
                raise CanonicalizationError(f"{path}: object keys must be ASCII strings")
            _check_profile(item, f"{path}.{key}")
        return
    raise CanonicalizationError(f"{path}: unsupported type {type(value).__name__}")


def canonical(value: Any) -> bytes:
    """RFC 8785 canonical JSON bytes for a value inside the restricted profile."""
    _check_profile(value)
    return rfc8785.dumps(value)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(hex_value: str, name: str) -> bytes:
    raw = bytes.fromhex(hex_value)
    if len(raw) != 32:
        raise ValueError(f"{name} must be a 32-byte SHA-256 digest")
    return raw


def payload_hash(payload: dict) -> str:
    return sha256_hex(PAYLOAD_DOMAIN + canonical(payload))


def event_hash(sequence: int, previous_event_hash: str, payload_hash_hex: str) -> str:
    if not 0 < sequence < 2**64:
        raise ValueError("sequence must be a positive 64-bit integer")
    return sha256_hex(
        EVENT_DOMAIN
        + sequence.to_bytes(8, "big")
        + _digest(previous_event_hash, "previous_event_hash")
        + _digest(payload_hash_hex, "payload_hash")
    )


def checkpoint_digest(body: dict) -> str:
    return sha256_hex(CHECKPOINT_DOMAIN + canonical(body))


# --- Merkle tree (RFC 9162 §2.1) ------------------------------------------------------------


def _leaf(event_hash_hex: str) -> bytes:
    return hashlib.sha256(b"\x00" + _digest(event_hash_hex, "leaf")).digest()


def _node(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _split(n: int) -> int:
    """Largest power of two strictly smaller than n (n >= 2)."""
    k = 1
    while k << 1 < n:
        k <<= 1
    return k


def _mth(leaves: list[bytes]) -> bytes:
    if len(leaves) == 1:
        return leaves[0]
    k = _split(len(leaves))
    return _node(_mth(leaves[:k]), _mth(leaves[k:]))


def merkle_root(event_hashes: list[str]) -> str:
    if not event_hashes:
        raise ValueError("a checkpoint must cover at least one event")
    return _mth([_leaf(h) for h in event_hashes]).hex()


def _path(m: int, leaves: list[bytes]) -> list[bytes]:
    if len(leaves) == 1:
        return []
    k = _split(len(leaves))
    if m < k:
        return _path(m, leaves[:k]) + [_mth(leaves[k:])]
    return _path(m - k, leaves[k:]) + [_mth(leaves[:k])]


def inclusion_proof(event_hashes: list[str], index: int) -> list[str]:
    if not 0 <= index < len(event_hashes):
        raise IndexError("leaf index outside the tree")
    return [h.hex() for h in _path(index, [_leaf(h) for h in event_hashes])]


def verify_inclusion(event_hash_hex: str, index: int, tree_size: int, proof: list[str], root_hex: str) -> bool:
    """RFC 9162 §2.1.3.2 inclusion proof verification."""
    if not 0 <= index < tree_size:
        return False
    fn, sn = index, tree_size - 1
    r = _leaf(event_hash_hex)
    for p_hex in proof:
        p = bytes.fromhex(p_hex)
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            r = _node(p, r)
            if not fn & 1:
                while fn and not fn & 1:
                    fn >>= 1
                    sn >>= 1
        else:
            r = _node(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r.hex() == root_hex
