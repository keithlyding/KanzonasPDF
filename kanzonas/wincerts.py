"""Sign with certificates from the Windows certificate store (like Adobe and PDF-XChange).

Lists the signing certificates in your Personal store (certmgr.msc > Personal > Certificates)
and signs through Windows itself, so certificates whose private key can't be exported, smart
cards and USB tokens work too: Windows asks for the PIN when a key needs one. The private key
never passes through KanzonasPDF.

Windows only (ctypes calls into crypt32 / ncrypt / advapi32). Imported only when signing.
"""

import ctypes
import datetime
import hashlib
from ctypes import wintypes as W

from pyhanko.sign import signers

# crypt32 constants
CERT_KEY_PROV_INFO_PROP_ID = 2
CRYPT_ACQUIRE_COMPARE_KEY_FLAG = 0x4
CRYPT_ACQUIRE_PREFER_NCRYPT_KEY_FLAG = 0x20000
CERT_NCRYPT_KEY_SPEC = 0xFFFFFFFF
BCRYPT_PAD_PKCS1 = 0x2
CALG = {"sha256": 0x800C, "sha384": 0x800D, "sha512": 0x800E}
HP_HASHVAL = 0x2
PROV_RSA_AES = 24
CRYPT_VERIFYCONTEXT = 0xF0000000


class CERT_CONTEXT(ctypes.Structure):
    _fields_ = [("dwCertEncodingType", W.DWORD), ("pbCertEncoded", ctypes.POINTER(ctypes.c_ubyte)),
                ("cbCertEncoded", W.DWORD), ("pCertInfo", ctypes.c_void_p),
                ("hCertStore", ctypes.c_void_p)]


PCCERT = ctypes.POINTER(CERT_CONTEXT)


class CERT_CHAIN_ELEMENT(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("pCertContext", PCCERT)]     # (rest not needed)


class CERT_SIMPLE_CHAIN(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("dwErrorStatus", W.DWORD), ("dwInfoStatus", W.DWORD),
                ("cElement", W.DWORD),
                ("rgpElement", ctypes.POINTER(ctypes.POINTER(CERT_CHAIN_ELEMENT)))]


class CERT_CHAIN_CONTEXT(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("dwErrorStatus", W.DWORD), ("dwInfoStatus", W.DWORD),
                ("cChain", W.DWORD),
                ("rgpChain", ctypes.POINTER(ctypes.POINTER(CERT_SIMPLE_CHAIN)))]


class CERT_CHAIN_PARA(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("dwType", W.DWORD), ("cUsageIdentifier", W.DWORD),
                ("rgpszUsageIdentifier", ctypes.c_void_p)]


class BCRYPT_PKCS1_PADDING_INFO(ctypes.Structure):
    _fields_ = [("pszAlgId", W.LPCWSTR)]


_libs = None


def _api():
    """Load the Windows libraries once and declare the functions used."""
    global _libs
    if _libs is None:
        c = ctypes.WinDLL("crypt32", use_last_error=True)
        n = ctypes.WinDLL("ncrypt", use_last_error=True)
        a = ctypes.WinDLL("advapi32", use_last_error=True)
        c.CertOpenSystemStoreW.argtypes = [ctypes.c_void_p, W.LPCWSTR]
        c.CertOpenSystemStoreW.restype = ctypes.c_void_p
        c.CertCloseStore.argtypes = [ctypes.c_void_p, W.DWORD]
        c.CertEnumCertificatesInStore.argtypes = [ctypes.c_void_p, PCCERT]
        c.CertEnumCertificatesInStore.restype = PCCERT
        c.CertGetCertificateContextProperty.argtypes = [PCCERT, W.DWORD, ctypes.c_void_p,
                                                        ctypes.POINTER(W.DWORD)]
        c.CertGetCertificateContextProperty.restype = W.BOOL
        c.CertDuplicateCertificateContext.argtypes = [PCCERT]
        c.CertDuplicateCertificateContext.restype = PCCERT
        c.CertFreeCertificateContext.argtypes = [PCCERT]
        c.CryptAcquireCertificatePrivateKey.argtypes = [
            PCCERT, W.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(W.DWORD), ctypes.POINTER(W.BOOL)]
        c.CryptAcquireCertificatePrivateKey.restype = W.BOOL
        c.CertGetCertificateChain.argtypes = [
            ctypes.c_void_p, PCCERT, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.POINTER(CERT_CHAIN_PARA), W.DWORD, ctypes.c_void_p,
            ctypes.POINTER(ctypes.POINTER(CERT_CHAIN_CONTEXT))]
        c.CertGetCertificateChain.restype = W.BOOL
        c.CertFreeCertificateChain.argtypes = [ctypes.POINTER(CERT_CHAIN_CONTEXT)]
        n.NCryptSignHash.argtypes = [ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, W.DWORD,
                                     ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD), W.DWORD]
        n.NCryptSignHash.restype = ctypes.c_long
        n.NCryptFreeObject.argtypes = [ctypes.c_size_t]
        a.CryptCreateHash.argtypes = [ctypes.c_size_t, W.DWORD, ctypes.c_size_t, W.DWORD,
                                      ctypes.POINTER(ctypes.c_size_t)]
        a.CryptCreateHash.restype = W.BOOL
        a.CryptSetHashParam.argtypes = [ctypes.c_size_t, W.DWORD, ctypes.c_void_p, W.DWORD]
        a.CryptSetHashParam.restype = W.BOOL
        a.CryptSignHashW.argtypes = [ctypes.c_size_t, W.DWORD, W.LPCWSTR, W.DWORD,
                                     ctypes.c_void_p, ctypes.POINTER(W.DWORD)]
        a.CryptSignHashW.restype = W.BOOL
        a.CryptDestroyHash.argtypes = [ctypes.c_size_t]
        a.CryptReleaseContext.argtypes = [ctypes.c_size_t, W.DWORD]
        _libs = (c, n, a)
    return _libs


def _der(ctx):
    return ctypes.string_at(ctx.contents.pbCertEncoded, ctx.contents.cbCertEncoded)


def _enum(store):
    c = _api()[0]
    ctx = c.CertEnumCertificatesInStore(store, None)
    while ctx:
        yield ctx
        ctx = c.CertEnumCertificatesInStore(store, ctx)   # frees the previous one


def _usable(cert):
    """Can this certificate sign documents? (key usage, if it says, allows signing)"""
    try:
        ku = cert.key_usage_value
    except Exception:
        return True
    if ku is None:
        return True
    return bool({"digital_signature", "non_repudiation"} & set(ku.native))


def list_certificates():
    """Signing certificates with a private key in the user's Personal store, newest first:
    dicts with name, issuer, email, expires (datetime), expired (bool), thumbprint."""
    from asn1crypto import x509
    c = _api()[0]
    store = c.CertOpenSystemStoreW(None, "MY")
    if not store:
        return []
    out = []
    try:
        for ctx in _enum(store):
            size = W.DWORD(0)
            if not c.CertGetCertificateContextProperty(ctx, CERT_KEY_PROV_INFO_PROP_ID, None,
                                                       ctypes.byref(size)):
                continue                                  # no private key: can't sign
            der = _der(ctx)
            try:
                cert = x509.Certificate.load(der)
                if not _usable(cert):
                    continue
                subj = cert.subject.native
                expires = cert["tbs_certificate"]["validity"]["not_after"].native
            except Exception:
                continue
            out.append({
                "name": subj.get("common_name") or cert.subject.human_friendly,
                "issuer": cert.issuer.native.get("common_name") or cert.issuer.human_friendly,
                "email": subj.get("email_address", ""),
                "expires": expires,
                "expired": expires < datetime.datetime.now(datetime.timezone.utc),
                "self_signed": cert.self_signed != "no",
                "thumbprint": hashlib.sha1(der).hexdigest(),
            })
    finally:
        c.CertCloseStore(store, 0)
    out.sort(key=lambda d: (d["expired"], -d["expires"].timestamp()))
    return out


def _find(store, thumbprint):
    c = _api()[0]
    for ctx in _enum(store):
        if hashlib.sha1(_der(ctx)).hexdigest() == thumbprint.lower():
            dup = c.CertDuplicateCertificateContext(ctx)
            c.CertFreeCertificateContext(ctx)             # stop the enumeration cleanly
            return dup
    return None


def _chain(ctx):
    """DER of the certificates above this one (intermediates and root), as Windows builds it."""
    c = _api()[0]
    para = CERT_CHAIN_PARA()
    para.cbSize = ctypes.sizeof(CERT_CHAIN_PARA)
    chain = ctypes.POINTER(CERT_CHAIN_CONTEXT)()
    if not c.CertGetCertificateChain(None, ctx, None, None, ctypes.byref(para), 0, None,
                                     ctypes.byref(chain)):
        return []
    try:
        if not chain.contents.cChain:
            return []
        simple = chain.contents.rgpChain[0].contents
        return [_der(simple.rgpElement[i].contents.pCertContext)
                for i in range(1, simple.cElement)]
    finally:
        c.CertFreeCertificateChain(chain)


def _sign_digest(ctx, digest, hash_name, ecdsa):
    """Have Windows sign a digest with the certificate's private key. RSA: PKCS#1 v1.5 bytes;
    ECDSA: raw r||s."""
    c, n, a = _api()
    key = ctypes.c_size_t(0)
    spec = W.DWORD(0)
    free = W.BOOL(False)
    if not c.CryptAcquireCertificatePrivateKey(
            ctx, CRYPT_ACQUIRE_COMPARE_KEY_FLAG | CRYPT_ACQUIRE_PREFER_NCRYPT_KEY_FLAG, None,
            ctypes.byref(key), ctypes.byref(spec), ctypes.byref(free)):
        raise OSError("Windows couldn't open the certificate's private key "
                      "(error %d). If it's on a card or token, plug it in." % ctypes.get_last_error())
    buf = ctypes.create_string_buffer(digest, len(digest))
    try:
        if spec.value == CERT_NCRYPT_KEY_SPEC:            # CNG key (most keys today)
            pad = BCRYPT_PKCS1_PADDING_INFO(hash_name.upper())
            pinfo, flags = (None, 0) if ecdsa else (ctypes.byref(pad), BCRYPT_PAD_PKCS1)
            size = W.DWORD(0)
            rc = n.NCryptSignHash(key.value, pinfo, buf, len(digest), None, 0,
                                  ctypes.byref(size), flags)
            if rc == 0:
                sig = ctypes.create_string_buffer(size.value)
                rc = n.NCryptSignHash(key.value, pinfo, buf, len(digest), sig, size,
                                      ctypes.byref(size), flags)
            if rc != 0:
                if rc & 0xFFFFFFFF == 0x800704C7:          # ERROR_CANCELLED (PIN dialog)
                    raise OSError("Signing was canceled.")
                raise OSError("Windows couldn't sign (error 0x%08X)." % (rc & 0xFFFFFFFF))
            return sig.raw[:size.value]
        # older CryptoAPI key (some smart card drivers)
        if ecdsa:
            raise OSError("This certificate's key type isn't supported for signing.")
        h = ctypes.c_size_t(0)
        if not a.CryptCreateHash(key.value, CALG[hash_name], 0, 0, ctypes.byref(h)):
            raise OSError("Windows couldn't sign with %s (error %d)."
                          % (hash_name.upper(), ctypes.get_last_error()))
        try:
            if not a.CryptSetHashParam(h.value, HP_HASHVAL, buf, 0):
                raise OSError("Windows couldn't sign (error %d)." % ctypes.get_last_error())
            size = W.DWORD(0)
            a.CryptSignHashW(h.value, spec.value, None, 0, None, ctypes.byref(size))
            sig = ctypes.create_string_buffer(size.value)
            if not a.CryptSignHashW(h.value, spec.value, None, 0, sig, ctypes.byref(size)):
                raise OSError("Windows couldn't sign (error %d)." % ctypes.get_last_error())
            return sig.raw[:size.value][::-1]             # CryptoAPI is little-endian
        finally:
            a.CryptDestroyHash(h.value)
    finally:
        if free.value:
            if spec.value == CERT_NCRYPT_KEY_SPEC:
                n.NCryptFreeObject(key.value)
            else:
                a.CryptReleaseContext(key.value, 0)


class WindowsSigner(signers.Signer):
    """pyHanko signer whose private-key operation is done by Windows."""

    def __init__(self, thumbprint):
        from asn1crypto import algos, x509
        from pyhanko_certvalidator.registry import SimpleCertificateStore
        c = _api()[0]
        store = c.CertOpenSystemStoreW(None, "MY")
        if not store:
            raise OSError("Couldn't open the Windows certificate store.")
        try:
            ctx = _find(store, thumbprint)
            if not ctx:
                raise OSError("That certificate is no longer in the Windows certificate store.")
            try:
                cert = x509.Certificate.load(_der(ctx))
                chain = [x509.Certificate.load(d) for d in _chain(ctx)]
            finally:
                c.CertFreeCertificateContext(ctx)
        finally:
            c.CertCloseStore(store, 0)
        self.thumbprint = thumbprint
        algo = cert.public_key.algorithm
        if algo not in ("rsa", "ec"):
            raise OSError("This certificate's key type (%s) isn't supported for signing." % algo)
        self.ecdsa = algo == "ec"
        self.key_bytes = (cert.public_key.bit_size + 7) // 8
        super().__init__(
            signing_cert=cert,
            cert_registry=SimpleCertificateStore.from_certs([cert] + chain),
            signature_mechanism=algos.SignedDigestAlgorithm(
                {"algorithm": "sha256_ecdsa" if self.ecdsa else "sha256_rsa"}))

    async def async_sign_raw(self, data, digest_algorithm, dry_run=False):
        from asn1crypto import algos
        if dry_run:                                        # size estimate only
            return bytes(2 * self.key_bytes + 16 if self.ecdsa else self.key_bytes)
        name = digest_algorithm.lower().replace("-", "")
        digest = hashlib.new(name, data).digest()
        c = _api()[0]
        store = c.CertOpenSystemStoreW(None, "MY")
        try:
            ctx = _find(store, self.thumbprint)
            if not ctx:
                raise OSError("That certificate is no longer in the Windows certificate store.")
            try:
                sig = _sign_digest(ctx, digest, name, self.ecdsa)
            finally:
                c.CertFreeCertificateContext(ctx)
        finally:
            c.CertCloseStore(store, 0)
        if self.ecdsa:
            sig = algos.DSASignature.from_p1363(sig).dump()
        return sig
