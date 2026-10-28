"""Pure cryptographic format tests (no database): canonical serialization, hash chain, Merkle proofs,
and agreement between the server implementation and the independent offline verifier."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import rfc8785

from app.trust import crypto

from verifier_path import verifier_path


def _load_verifier():
    spec = importlib.util.spec_from_file_location("verify_receipt", verifier_path())
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = _load_verifier()


def test_canonical_serialization_is_deterministic_and_rfc8785() -> None:
    a = {"b": 1, "a": {"z": [3, 2, 1], "y": "क्लीन"}, "c": None, "d": True}
    b = json.loads(json.dumps(a))  # different construction order / object identity
    b = {"d": True, "c": None, "a": {"y": "क्लीन", "z": [3, 2, 1]}, "b": 1}
    assert crypto.canonical(a) == crypto.canonical(b) == rfc8785.dumps(a)
    assert crypto.canonical(a) == b'{"a":{"y":"\xe0\xa4\x95\xe0\xa5\x8d\xe0\xa4\xb2\xe0\xa5\x80\xe0\xa4\xa8","z":[3,2,1]},"b":1,"c":null,"d":true}'


def test_verifier_fallback_canonicalization_equals_jcs_for_the_profile() -> None:
    sample = {"k": "line\nbreak \"q\" \\ \u0001 \u007f", "n": -5, "arr": [{"b": 2, "a": 1}], "t": False}
    fallback = json.dumps(sample, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert fallback == rfc8785.dumps(sample) == verifier.canonical(sample)


@pytest.mark.parametrize("bad", [{"x": 1.5}, {"x": 2**60}, {"é": 1}])
def test_profile_rejects_ambiguous_values(bad) -> None:
    with pytest.raises(crypto.CanonicalizationError):
        crypto.canonical(bad)


def test_event_hash_byte_layout_and_domain_separation() -> None:
    payload = {"format": crypto.EVENT_FORMAT, "x": 1}
    ph = crypto.payload_hash(payload)
    assert ph == hashlib.sha256(b"SAHAKAR-SEVA:financial-event-payload:v1\x00" + b'{"format":"sahakar-seva/financial-event/v1","x":1}').hexdigest()
    eh = crypto.event_hash(1, crypto.GENESIS_HASH, ph)
    expected = hashlib.sha256(b"SAHAKAR-SEVA:financial-event:v1\x00" + (1).to_bytes(8, "big") + bytes(32) + bytes.fromhex(ph)).hexdigest()
    assert eh == expected == verifier.event_hash(1, crypto.GENESIS_HASH, ph)
    # Same inputs at a different sequence, or with a different predecessor, give a different hash.
    assert crypto.event_hash(2, crypto.GENESIS_HASH, ph) != eh
    assert crypto.event_hash(1, "11" * 32, ph) != eh
    with pytest.raises(ValueError):
        crypto.event_hash(1, "00" * 31, ph)  # wrong-length digest is never accepted


def _chain(n: int) -> list[dict]:
    events, prev = [], crypto.GENESIS_HASH
    for seq in range(1, n + 1):
        payload = {"format": crypto.EVENT_FORMAT, "seq_marker": seq, "amount_paise": 50000}
        ph = crypto.payload_hash(payload)
        eh = crypto.event_hash(seq, prev, ph)
        events.append({"sequence": seq, "payload": payload, "payload_hash": ph, "previous_event_hash": prev, "event_hash": eh})
        prev = eh
    return events


def test_hash_chain_continuity_detects_edit_and_reorder() -> None:
    from app.trust.integrity import verify_event_chain

    events = [
        {"id": str(i), "sequence": e["sequence"], "event_type": "x", "booking_id": None,
         "payload_canonical": crypto.canonical({**e["payload"], "event_type": "x", "booking_id": None}).decode(),
         } for i, e in enumerate(_chain(4))
    ]
    prev = crypto.GENESIS_HASH
    for e in events:  # rebuild real hashes for the stored-row shape
        e["payload_hash"] = crypto.payload_hash(json.loads(e["payload_canonical"]))
        e["previous_event_hash"] = prev
        e["event_hash"] = crypto.event_hash(e["sequence"], prev, e["payload_hash"])
        prev = e["event_hash"]
    assert verify_event_chain(events) == []

    edited = [dict(e) for e in events]
    edited[1]["payload_canonical"] = edited[1]["payload_canonical"].replace("50000", "40000")
    assert {p["code"] for p in verify_event_chain(edited)} >= {"PAYLOAD_HASH_MISMATCH"}

    reordered = [events[0], events[2], events[1], events[3]]
    codes = {p["code"] for p in verify_event_chain(reordered)}
    assert "SEQUENCE_GAP_OR_REORDER" in codes and "CHAIN_BROKEN" in codes

    removed = [events[0], events[2], events[3]]
    assert "SEQUENCE_GAP_OR_REORDER" in {p["code"] for p in verify_event_chain(removed)}


@pytest.mark.parametrize("n", list(range(1, 18)))
def test_merkle_inclusion_proofs_verify_for_every_leaf(n: int) -> None:
    hashes = [e["event_hash"] for e in _chain(n)]
    root = crypto.merkle_root(hashes)
    for i, h in enumerate(hashes):
        proof = crypto.inclusion_proof(hashes, i)
        assert crypto.verify_inclusion(h, i, n, proof, root)
        assert verifier.verify_inclusion(h, i, n, proof, root)
        if n > 1:
            assert not crypto.verify_inclusion(hashes[(i + 1) % n], i, n, proof, root)  # different leaf
            assert not crypto.verify_inclusion(h, (i + 1) % n, n, proof, root)  # claimed at another position
        assert not crypto.verify_inclusion(h, i, n, proof, "00" * 32)  # different root
        # The tree size is bound by the checkpoint body (event_count), which the verifiers compare separately.


def test_merkle_root_matches_rfc9162_definition() -> None:
    hashes = [e["event_hash"] for e in _chain(3)]
    leaf = lambda h: hashlib.sha256(b"\x00" + bytes.fromhex(h)).digest()  # noqa: E731
    node = lambda a, b: hashlib.sha256(b"\x01" + a + b).digest()  # noqa: E731
    expected = node(node(leaf(hashes[0]), leaf(hashes[1])), leaf(hashes[2])).hex()
    assert crypto.merkle_root(hashes) == expected


def test_checkpoint_digest_recomputation_matches_both_implementations() -> None:
    body = {"format": crypto.CHECKPOINT_FORMAT, "checkpoint_index": 1, "first_sequence": 1, "last_sequence": 3,
            "merkle_root": "ab" * 32, "previous_checkpoint_digest": crypto.GENESIS_HASH}
    expected = hashlib.sha256(b"SAHAKAR-SEVA:checkpoint:v1\x00" + rfc8785.dumps(body)).hexdigest()
    assert crypto.checkpoint_digest(body) == expected == verifier.checkpoint_digest(body)
    assert crypto.checkpoint_digest({**body, "last_sequence": 2}) != expected
