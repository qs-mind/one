"""What the core is: its version, whether it is the installed app, and its native libraries.

`native()` loads every native library the core ships once and says which version came, so the
packaging smoke test (Plan 8 Task 3) proves the embedded Python can load them all.
"""

import importlib.util
import os
from importlib.metadata import version

import qsone
from qsone.records.pdfium_guard import PDFIUM


def about() -> dict:
    return {"version": qsone.__version__, "release": os.environ.get("QSONE_RELEASE") == "1"}


def native() -> dict:
    import cryptography
    import keyring

    with PDFIUM:
        import pypdfium2
    import sqlcipher3.dbapi2 as sqlcipher
    import sqlite_vec
    import tokenizers
    import typst  # noqa: F401 - its Rust extension loads on import
    import wasmtime
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    conn = sqlcipher.connect(":memory:")
    try:
        conn.execute(f"PRAGMA key = \"x'{'11' * 32}'\"")
        cipher = conn.execute("PRAGMA cipher_version").fetchone()[0]
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        vec = conn.execute("SELECT vec_version()").fetchone()[0]
    finally:
        conn.close()

    AESGCM(AESGCM.generate_key(bit_length=256))  # the Rust binding loads
    with PDFIUM:
        pdfium = pypdfium2.PDFIUM_INFO  # the pdfium library is opened on import
    wasmtime.Engine()
    onnx = None
    if importlib.util.find_spec("onnxruntime") is not None:  # no wheel for Intel Macs
        import onnxruntime

        onnxruntime.get_available_providers()
        onnx = onnxruntime.__version__
    backend = keyring.get_keyring()
    return {
        "sqlcipher": cipher,
        "sqlite_vec": vec,
        "pdfium": str(pdfium),
        "onnxruntime": onnx,
        "tokenizers": tokenizers.__version__,
        "wasmtime": version("wasmtime"),
        "typst": version("typst"),
        "keyring_backend": f"{type(backend).__module__}.{type(backend).__name__}",
        "cryptography": cryptography.__version__,
    }
