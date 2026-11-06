"""The search model, pinned to an exact Hugging Face commit with each file's size and SHA-256.

multilingual-e5-small, int8 ONNX (founder's decision, 5 Nov 2026): 135 MB with its tokenizer,
instead of the 1.17 GB of BGE-M3 and its reranker. Only `tokenizer.json` and the int8 `.onnx`
are fetched.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelFile:
    path: str  # inside the repo
    size: int
    sha256: str


@dataclass(frozen=True)
class ModelSpec:
    id: str  # folder name
    repo: str
    revision: str  # full commit on Hugging Face
    files: tuple[ModelFile, ...]
    licence: str
    dims: int
    ram_bytes: int  # measured lean peak (spike §4 method), for the RAM budget

    @property
    def name(self) -> str:
        """Kept in the project file's meta.embed_model."""
        return f"{self.repo}@{self.revision[:12]}"

    def url(self, f: ModelFile) -> str:
        return f"https://huggingface.co/{self.repo}/resolve/{self.revision}/{f.path}"

    @property
    def size(self) -> int:
        return sum(f.size for f in self.files)


# Xenova's ONNX export of intfloat/multilingual-e5-small (MIT). `model_quantized` is int8 with
# reduce_range, so it keeps its accuracy on AVX2 laptops without VNNI too.
EMBEDDER = ModelSpec(
    id="multilingual-e5-small-int8",
    repo="Xenova/multilingual-e5-small",
    revision="761b726dd34fb83930e26aab4e9ac3899aa1fa78",
    files=(
        ModelFile(
            "tokenizer.json",
            17_082_730,
            "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39",
        ),
        ModelFile(
            "onnx/model_quantized.onnx",
            118_308_185,
            "f80102d3f2a1229f387d3c81909990d8945513e347b0eab049f7de3c6f98c193",
        ),
    ),
    licence="MIT",
    dims=384,
    ram_bytes=700_000_000,  # 0.64 GB measured (5 Nov 2026, batch 4, no arena), rounded up
)

MODELS = (EMBEDDER,)  # 135,390,915 bytes in all

# Folders of models One no longer uses, deleted from its cache once the new one is ready.
RETIRED = ("bge-m3-int8", "bge-reranker-v2-m3-int8")
