"""Certificate-based digital signatures (pyHanko, MIT).

A digital signature proves who signed and that the file hasn't changed since. You can
sign with a certificate file from a certificate authority / your company (.pfx/.p12), or
with a personal certificate the app creates for you. A personal (self-signed) certificate
proves the document is unchanged, but other people's software can't confirm your
identity unless they choose to trust your certificate. The certificate this app creates
is an end-entity document signer: it is not a certificate authority and cannot issue
other certificates.
"""

import datetime
import hashlib
import io
import json
import logging
import os


from . import annotations as A

for _name in ("pyhanko", "pyhanko_certvalidator"):
    logging.getLogger(_name).setLevel(logging.CRITICAL)


def my_cert_path():
    from . import paths
    return os.path.join(paths.data_dir(), "my-certificate.p12")


def create_certificate(name, email, org, password, path=None):
    """Self-signed signing certificate (RSA 2048, 10 years) saved as a password-protected .p12."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, name)]
    if org:
        attrs.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, org))
    if email:
        attrs.append(x509.NameAttribute(NameOID.EMAIL_ADDRESS, email))
    subject = x509.Name(attrs)
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True,
                                         key_encipherment=False, data_encipherment=False,
                                         key_agreement=False, key_cert_sign=False, crl_sign=False,
                                         encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.EMAIL_PROTECTION,
                x509.ObjectIdentifier("1.3.6.1.5.5.7.3.36"),
            ]), critical=False)
            .sign(key, hashes.SHA256()))
    data = pkcs12.serialize_key_and_certificates(
        name.encode(), key, cert, None, serialization.BestAvailableEncryption(password.encode()))
    path = path or my_cert_path()
    with open(path, "wb") as f:
        f.write(data)
    return path


def load_signer(path, password):
    from pyhanko.sign import signers
    signer = signers.SimpleSigner.load_pkcs12(path, passphrase=password.encode() if password else None)
    if signer is None:
        raise ValueError("Couldn't open that certificate. Is the password right?")
    return signer


def sign(pdf_bytes, out_path, signer, reason="", location="", lock=False):
    """Sign (optionally certify with 'no changes allowed') and write out_path."""
    from pyhanko.sign import signers, fields
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.pdf_utils.reader import PdfFileReader
    existing = len(PdfFileReader(io.BytesIO(pdf_bytes)).embedded_signatures)
    w = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes))
    meta = signers.PdfSignatureMetadata(
        field_name=f"KZSignature{existing + 1}", reason=reason or None,
        location=location or None, certify=lock and existing == 0,
        docmdp_permissions=fields.MDPPerm.NO_CHANGES if lock else fields.MDPPerm.FILL_FORMS)
    out = io.BytesIO()
    signers.sign_pdf(w, meta, signer=signer, output=out)
    with open(out_path, "wb") as f:
        f.write(out.getvalue())
    return out_path


# Free public RFC 3161 time servers (no account needed). HTTPS only: the token is signed,
# but the request should not go out in the clear.
TIME_SERVERS = ["https://timestamp.digicert.com", "https://timestamp.sectigo.com",
                "https://freetsa.org/tsr"]


def timestamp(pdf_bytes, out_path, url, timestamper=None):
    """Add a document timestamp from a trusted time server (proves the file existed, unchanged,
    at that time). timestamper can be given for testing."""
    from pyhanko.sign import signers, timestamps
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    ts = timestamper or timestamps.HTTPTimeStamper(url, timeout=20)
    w = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes))
    out = io.BytesIO()
    signers.PdfTimeStamper(ts).timestamp_pdf(w, "sha256", output=out)
    with open(out_path, "wb") as f:
        f.write(out.getvalue())
    return out_path


# ---- trust & validation -------------------------------------------------------------
def _trusted():
    try:
        return set(json.loads(A._settings().value("trusted_certs", "[]") or "[]"))
    except (ValueError, TypeError):
        return set()


def trust(fingerprint):
    t = _trusted()
    t.add(fingerprint)
    A._settings().setValue("trusted_certs", json.dumps(sorted(t)))


def validate(pdf_bytes):
    """[{name, email, time, reason, intact, modified, trusted, fingerprint, summary, ok}]"""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko.sign.validation.status import SignatureCoverageLevel
    from pyhanko_certvalidator import ValidationContext
    reader = PdfFileReader(io.BytesIO(pdf_bytes), strict=False)
    trusted = _trusted()
    results = []
    for sig in reader.embedded_signatures:
        try:
            is_ts = str(sig.sig_object.get("/Type", "")) == "/DocTimeStamp"
        except Exception:
            is_ts = False
        if is_ts:
            results.append(_validate_timestamp(sig))
            continue
        info = {"field": sig.field_name, "name": "", "email": "", "time": None, "reason": "",
                "intact": False, "modified": True, "trusted": False, "fingerprint": ""}
        try:
            cert = sig.signer_cert
            info["fingerprint"] = hashlib.sha256(cert.dump()).hexdigest()
            native = cert.subject.native
            info["name"] = native.get("common_name", "") or cert.subject.human_friendly
            info["email"] = native.get("email_address", "")
            st = validate_pdf_signature(sig, ValidationContext(trust_roots=[], allow_fetching=False))
            info["intact"] = bool(st.intact and st.valid)
            info["time"] = st.signer_reported_dt
            if st.coverage == SignatureCoverageLevel.ENTIRE_FILE:
                info["modified"] = False
            else:
                level = str(getattr(st, "modification_level", "") or "OTHER").split(".")[-1]
                info["modified"] = level not in ("NONE", "LTA_UPDATES", "FORM_FILLING")
            info["trusted"] = bool(st.trusted) or info["fingerprint"] in trusted
            try:
                info["reason"] = sig.sig_object.get("/Reason", "") or ""
            except Exception:
                pass
        except Exception as ex:
            info["error"] = str(ex)
        info["ok"] = info["intact"] and not info["modified"]
        when = info["time"].strftime("%Y-%m-%d %H:%M") if info["time"] else "unknown time"
        if not info["intact"]:
            state = "INVALID: the signed content was changed or the signature is damaged"
        elif info["modified"]:
            state = "changes were made after signing"
        else:
            state = "unchanged since signing"
        who = "identity confirmed" if info["trusted"] else \
            "identity not verified (certificate not trusted on this computer)"
        info["summary"] = f"Signed by {info['name'] or 'unknown'} on {when}: {state}; {who}."
        results.append(info)
    return results


def _validate_timestamp(sig):
    from pyhanko.sign.validation import validate_pdf_timestamp
    from pyhanko_certvalidator import ValidationContext
    info = {"field": sig.field_name, "timestamp": True, "intact": False, "modified": True,
            "trusted": False, "name": "", "time": None}
    try:
        st = validate_pdf_timestamp(sig, validation_context=ValidationContext(
            trust_roots=[], allow_fetching=False))
        info["intact"] = bool(st.intact and st.valid)
        info["time"] = getattr(st, "timestamp", None)
        info["modified"] = False
        cert = sig.signer_cert
        info["name"] = cert.subject.native.get("common_name", "") or cert.subject.human_friendly
    except Exception as ex:
        info["error"] = str(ex)
    info["ok"] = info["intact"]
    when = info["time"].strftime("%Y-%m-%d %H:%M") if info["time"] else "unknown time"
    info["summary"] = (f"Timestamped by {info['name'] or 'a time server'} on {when}" +
                       (": unchanged since." if info["ok"] else ": INVALID or changed."))
    return info
