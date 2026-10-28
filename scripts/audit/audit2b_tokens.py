import base64, copy, datetime as dt, json, os, re, ssl, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "api")); sys.path.insert(0, str(ROOT / "services" / "api" / "tests"))
from common import *
from app.trust import timestamping, crypto
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from tsa_double import make_tsa, TestTsa, _name

base = json.load(open(OUT / "retained_worker_receipt.json"))        # genuine audit receipt (DigiCert token) from Audit 1
cp = base["checkpoints"][-1]; DIGEST = cp["digest"]; NONCE = int(cp["external_timestamp"]["request_nonce"])
TOKEN = base64.b64decode(cp["external_timestamp"]["time_stamp_response_der_b64"])
tmp = Path(tempfile.mkdtemp())
GENTIME = cp["external_timestamp"]["gen_time"]; gt = int(dt.datetime.strptime(GENTIME[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp())
pem = open("/Users/shresthchauhan/.agentflow/.venv/lib/python3.14/site-packages/certifi/cacert.pem").read()
G2 = tmp / "digicert_global_g2.pem"; G2.write_text(re.search(r"# Label: \"DigiCert Global Root G2\".*?(-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----)", pem, re.S).group(1) + "\n")
attacker = make_tsa(tmp / "att", "Attacker")

def v_openssl(der, digest, root):
    f = tmp / "t.tsr"; f.write_bytes(der)
    r = subprocess.run(["openssl","ts","-verify","-digest",digest,"-in",str(f),"-CAfile",str(root),"-attime",str(gt)], capture_output=True, text=True); return "Verification: OK" in (r.stdout + r.stderr)
def v_server(der, digest, root):
    try: timestamping.verify_response(der, digest, str(root), NONCE); return True
    except timestamping.TimestampError: return False
def v_cli(der, digest, root, body_mut=None):
    r = copy.deepcopy(base); c = r["checkpoints"][-1]; c["external_timestamp"]["time_stamp_response_der_b64"] = base64.b64encode(der).decode()
    if body_mut: body_mut(c)
    c["digest"] = digest if digest != DIGEST else c["digest"]
    p = save("a2_tokenvar.json", r); return verify(p, "--tsa-ca", root)["result"] == "EXTERNALLY TIMESTAMPED AND VERIFIED"

def flip(b, i): x = bytearray(b); x[i] ^= 0x01; return bytes(x)
d32 = bytes.fromhex(DIGEST); pos = TOKEN.find(d32); gpos = TOKEN.find(GENTIME[:19].replace("-", "").replace(":", "").replace("T", "").encode())
muts = {
  "genuine token, pinned DigiCert root (control)": (TOKEN, DIGEST, DIGICERT_ROOT, True),
  "flip 1 bit in CMS signature value": (flip(TOKEN, len(TOKEN) - 20), DIGEST, DIGICERT_ROOT, False),
  "flip 1 bit in the signed imprint (inside TSTInfo)": (flip(TOKEN, pos + 3), DIGEST, DIGICERT_ROOT, False),
  "alter genTime digit in signed TSTInfo": (flip(TOKEN, gpos + 10), DIGEST, DIGICERT_ROOT, False),
  "flip 1 bit inside an embedded certificate": (flip(TOKEN, 400), DIGEST, DIGICERT_ROOT, False),
  "truncate token": (TOKEN[:-60], DIGEST, DIGICERT_ROOT, False),
  "token checked against an ALTERED checkpoint digest": (TOKEN, DIGEST[:-1] + ("0" if DIGEST[-1] != "0" else "1"), DIGICERT_ROOT, False),
  "token for a different checkpoint (dev checkpoint 1)": (base64.b64decode(json.load(open('/tmp/sahakar-audit/a2/cp1.json'))["time_stamp_response_der_b64"]), DIGEST, DIGICERT_ROOT, False),
  "genuine token, WRONG trusted root (DigiCert Global Root G2)": (TOKEN, DIGEST, G2, False),
  "genuine token, root = attacker CA": (TOKEN, DIGEST, attacker.ca_pem, False),
  "attacker-signed token (valid under attacker CA), DigiCert root": (attacker.reply(timestamping.build_request(DIGEST, NONCE).der), DIGEST, DIGICERT_ROOT, False),
  "fake: random bytes": (os.urandom(len(TOKEN)), DIGEST, DIGICERT_ROOT, False),
  "fake: empty": (b"", DIGEST, DIGICERT_ROOT, False),
}
print(f"{'case':66s} openssl server  CLI   (expected genuine=accept, all else reject)")
for name, (der, dg, root, expect) in muts.items():
    a, b, c = v_openssl(der, dg, root), v_server(der, dg, root), v_cli(der, dg, root)
    check(f"{name:64s} {str(a):7s} {str(b):7s} {str(c):6s}", a == b == c == expect)

print("\n== certificate-purpose / validity abuses (the signer is issued by a TRUSTED test CA but is not a valid timestamping cert) ==")
def make_variant(label, eku, critical=True, not_after_delta=dt.timedelta(days=1), not_before_delta=dt.timedelta(minutes=-5)):
    d = tmp / label; d.mkdir(); now = dt.datetime.now(dt.timezone.utc)
    ca_k = ec.generate_private_key(ec.SECP256R1())
    ca = (x509.CertificateBuilder().subject_name(_name("V Root")).issuer_name(_name("V Root")).public_key(ca_k.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - dt.timedelta(days=3)).not_valid_after(now + dt.timedelta(days=3)).add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), True).add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_k.public_key()), False).sign(ca_k, hashes.SHA256()))
    k = ec.generate_private_key(ec.SECP256R1())
    b = (x509.CertificateBuilder().subject_name(_name("V TSA")).issuer_name(ca.subject).public_key(k.public_key()).serial_number(x509.random_serial_number())
         .not_valid_before(now + not_before_delta).not_valid_after(now + not_after_delta).add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
         .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_k.public_key()), False))
    if eku is not None: b = b.add_extension(x509.ExtendedKeyUsage(eku), critical)
    cert = b.sign(ca_k, hashes.SHA256()); P = serialization.Encoding.PEM
    (d / "ca.pem").write_bytes(ca.public_bytes(P)); (d / "tsa.pem").write_bytes(cert.public_bytes(P)); (d / "tsa.key").write_bytes(k.private_bytes(P, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (d / "serial").write_text("01\n"); (d / "tsa.cnf").write_text(f"[ tsa ]\ndefault_tsa = t\n[ t ]\nserial = {d/'serial'}\ncrypto_device = builtin\nsigner_digest = sha256\ndefault_policy = 1.3.6.1.4.1.99999.1\ndigests = sha256\naccuracy = secs:1\nordering = no\ntsa_name = no\ness_cert_id_chain = no\ness_cert_id_alg = sha256\n")
    return TestTsa(d, d / "ca.pem", d / "tsa.pem", d / "tsa.key", d / "tsa.cnf")
variants = {
  "valid timeStamping EKU, critical (control: should be accepted under its own CA)": (make_variant("ok", [ExtendedKeyUsageOID.TIME_STAMPING]), True),
  "signer has NO extended key usage": (make_variant("noeku", None), False),
  "signer EKU is serverAuth only": (make_variant("server", [ExtendedKeyUsageOID.SERVER_AUTH]), False),
  "timeStamping EKU present but NOT critical": (make_variant("noncrit", [ExtendedKeyUsageOID.TIME_STAMPING], critical=False), False),
  "signer certificate already expired at token time": (make_variant("expired", [ExtendedKeyUsageOID.TIME_STAMPING], not_before_delta=dt.timedelta(days=-2), not_after_delta=dt.timedelta(minutes=-1)), False),
}
for name, (tsa, expect) in variants.items():
    # stock OpenSSL cannot even SIGN with a non-timestamping signer; so test the X.509 purpose check that `ts -verify` uses.
    r = subprocess.run(["openssl","verify","-purpose","timestampsign","-CAfile",str(tsa.ca_pem),"-attime",str(int(dt.datetime.now(dt.timezone.utc).timestamp())),str(tsa.tsa_pem)], capture_output=True, text=True)
    accepted = r.returncode == 0 and ": OK" in r.stdout
    try:
        req = timestamping.build_request(DIGEST, NONCE); der = tsa.reply(req.der); signed = True
    except subprocess.CalledProcessError: signed = False
    if signed:
        globals()["gt"] = int(dt.datetime.now(dt.timezone.utc).timestamp())
        a, b, c = v_openssl(der, DIGEST, tsa.ca_pem), v_server(der, DIGEST, tsa.ca_pem), v_cli(der, DIGEST, tsa.ca_pem); detail = f"token: openssl={a} server={b} CLI={c}"; got = a and b and c
        ok = (a == b == c == expect)
    else:
        detail = "OpenSSL refused to sign"; got = False; ok = (accepted == expect) and (expect is False)
    check(f"{name:70s} purpose-check accepts={accepted}; {detail}", ok if not signed else ok and accepted == expect)
ok = sum(1 for r in RESULTS if r[1]); print(f"\n{ok}/{len(RESULTS)}"); save("audit2b_results.json", RESULTS)
