# QS Mind One

An agentic desktop app for the whole quantity surveying profession, in Arabic and English.
Every number has a source.

تطبيق سطح مكتب بوكلاء ذكاء اصطناعي لكل شغل مهندس الكميات، بالعربي والإنجليزي.
كل رقم له مصدر.

Status: design stage. Nothing to install yet.

License: [FSL-1.1-ALv2](LICENSE.md). Each version becomes Apache-2.0 two years after its release.

## Search models

Search by meaning uses two free models that One downloads once, when the engineer presses Download
in Project Records (1.17 GB from huggingface.co). They then run on the computer, on the CPU, without
internet. They are never in the installer or the repo.

| Model | File | Licence |
|---|---|---|
| [Xenova/bge-m3](https://huggingface.co/Xenova/bge-m3) (BGE-M3) | `onnx/model_int8.onnx`, `tokenizer.json` | MIT |
| [onnx-community/bge-reranker-v2-m3-ONNX](https://huggingface.co/onnx-community/bge-reranker-v2-m3-ONNX) | `onnx/model_int8.onnx`, `tokenizer.json` | Apache-2.0 |

Each file is pinned to an exact commit, size and SHA-256 in `core/qsone/meaning/manifest.py`; a file
is used only once its SHA-256 matches. They are stored in `<app data folder>/models/<model>/<commit>/`:
`%LOCALAPPDATA%\app.qsmind.one` on Windows, `~/Library/Application Support/app.qsmind.one` on macOS
and `~/.local/share/app.qsmind.one` on Linux. On Intel Macs (no onnxruntime wheel) search is by words
only.

Tests never download them. One opt-in test runs the real models; it downloads them into the folder
you name the first time, and needs about 4 GB of RAM, so run it alone:

```sh
QSONE_REAL_MODELS="$HOME/.cache/qsone-real-models" node scripts/python.mjs -m pytest core/tests/test_real_models.py -v -s
```
