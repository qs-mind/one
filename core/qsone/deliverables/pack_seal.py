"""A local, self-signed integrity seal. No certificate authority or network service."""

import base64
from datetime import UTC, datetime, timedelta
from io import BytesIO
from threading import Lock

import keyring
from asn1crypto import keys as asn_keys
from asn1crypto import x509 as asn_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from keyring.errors import KeyringError
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko_certvalidator.registry import SimpleCertificateStore

from qsone import copy
from qsone.keys import SERVICE
from qsone.records.project import RecordsError

_LOCK = Lock()
_USER = "pack-integrity-seal-v1"


def _identity():
    with _LOCK:
        saved = keyring.get_password(SERVICE, _USER)
        if saved is None:
            key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ONE local integrity seal")])
            now = datetime.now(UTC)
            cert = (
                x509.CertificateBuilder()
                .subject_name(name)
                .issuer_name(name)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=5))
                .not_valid_after(now + timedelta(days=3650))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(
                    x509.KeyUsage(True, True, False, False, False, False, False, False, False),
                    critical=True,
                )
                .sign(key, hashes.SHA256())
            )
            raw_key = key.private_bytes(
                serialization.Encoding.DER,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
            raw_cert = cert.public_bytes(serialization.Encoding.DER)
            saved = base64.b64encode(raw_key).decode() + ":" + base64.b64encode(raw_cert).decode()
            keyring.set_password(SERVICE, _USER, saved)
        key_data, cert_data = (base64.b64decode(s) for s in saved.split(":"))
    return signers.SimpleSigner(
        signing_cert=asn_x509.Certificate.load(cert_data),
        signing_key=asn_keys.PrivateKeyInfo.load(key_data),
        cert_registry=SimpleCertificateStore(),
    )


def seal(data: bytes) -> bytes:
    try:
        signer = _identity()
    except (KeyringError, ValueError):
        raise RecordsError(copy.PACK_KEY_UNAVAILABLE, status=503) from None
    out = BytesIO()
    signers.sign_pdf(
        IncrementalPdfFileWriter(BytesIO(data)),
        signers.PdfSignatureMetadata(field_name="ONEIntegritySeal"),
        signer=signer,
        output=out,
    )
    return out.getvalue()
