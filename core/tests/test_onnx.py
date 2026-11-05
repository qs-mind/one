"""The search model on onnxruntime, with a fake session and a tiny tokenizer: no model file."""

import ast
import math
from pathlib import Path

import pytest

pytest.importorskip("onnxruntime", reason="no onnxruntime here (Intel Mac)")

import numpy as np  # noqa: E402
from tokenizers import Tokenizer  # noqa: E402
from tokenizers.models import WordLevel  # noqa: E402
from tokenizers.pre_tokenizers import WhitespaceSplit  # noqa: E402
from tokenizers.processors import TemplateProcessing  # noqa: E402

from qsone.meaning import onnx  # noqa: E402
from qsone.meaning.manifest import EMBEDDER  # noqa: E402
from qsone.meaning.onnx import OnnxEmbedder, default_threads, session_options  # noqa: E402

WORDS = [
    "query:",
    "passage:",
    "خرسانة",
    "مسلحة",
    "للأسقف",
    "عينة",
    "عزل",
    "steel",
    "bars",
    "sample",
]
SPECIAL = ["<s>", "<pad>", "</s>", "<unk>"]
VOCAB = {w: i for i, w in enumerate(SPECIAL + WORDS)}
PAD = VOCAB["<pad>"]


def tiny_tokenizer() -> Tokenizer:
    t = Tokenizer(WordLevel(VOCAB, unk_token="<unk>"))
    t.pre_tokenizer = WhitespaceSplit()
    t.post_processor = TemplateProcessing(
        single="<s> $A </s>", special_tokens=[("<s>", VOCAB["<s>"]), ("</s>", VOCAB["</s>"])]
    )
    return t


class _Arg:
    def __init__(self, name):
        self.name = name


class FakeSession:
    """Declares its inputs, records every feed, and answers like the model would: each token's
    row is 1.0 at (its id mod dims). A padding row is 100 everywhere, so a mean that took it in
    would show."""

    def __init__(self, dims=8, inputs=("input_ids", "attention_mask"), output="last_hidden_state"):
        self.dims, self.inputs, self.output, self.feeds = dims, inputs, output, []

    def get_inputs(self):
        return [_Arg(n) for n in self.inputs]

    def get_outputs(self):
        return [_Arg(self.output)]

    def run(self, names, feed):
        assert names == [self.output]
        self.feeds.append(feed)
        ids = feed["input_ids"]
        out = np.zeros((*ids.shape, self.dims), dtype=np.float32)
        for (row, col), token in np.ndenumerate(ids):
            if token == PAD:
                out[row, col] = 100.0
            else:
                out[row, col, token % self.dims] = 1.0
        return [out]


def expected(text: str, dims: int = 8) -> list[float]:
    """The mean of the real tokens' rows, L2-normalised, worked out by hand."""
    ids = [VOCAB["<s>"], *(VOCAB[w] for w in text.split()), VOCAB["</s>"]]
    v = [0.0] * dims
    for i in ids:
        v[i % dims] += 1 / len(ids)
    size = math.sqrt(sum(x * x for x in v))
    return [x / size for x in v]


def embedder(session=None, dims=8) -> OnnxEmbedder:
    return OnnxEmbedder(tiny_tokenizer(), session or FakeSession(dims), name="x", dims=dims)


def test_passages_and_queries_get_their_prefixes():
    s = FakeSession()
    emb = embedder(s)
    emb.embed_documents(["عزل"])
    emb.embed_query("عزل")
    first = [VOCAB[w] for w in ["<s>", "passage:", "عزل", "</s>"]]
    second = [VOCAB[w] for w in ["<s>", "query:", "عزل", "</s>"]]
    assert [f["input_ids"][0].tolist() for f in s.feeds] == [first, second]
    assert emb.embed_query("عزل") != emb.embed_documents(["عزل"])[0]  # the prefix counts


def test_mean_of_the_tokens_without_padding_normalised_in_input_order():
    emb = embedder()
    texts = ["خرسانة مسلحة للأسقف عينة", "عزل", "steel bars sample"]
    out = emb.embed_documents(texts)  # batched together, so "عزل" is padded
    for text, v in zip(texts, out, strict=True):
        assert v == pytest.approx(expected(f"passage: {text}"))
    assert [round(math.hypot(*v), 6) for v in out] == [1.0, 1.0, 1.0]
    assert emb.embed_query("عزل") == pytest.approx(expected("query: عزل"))


def test_the_shipped_size_is_384():
    emb = embedder(FakeSession(dims=EMBEDDER.dims), dims=EMBEDDER.dims)
    (v,) = emb.embed_documents(["خرسانة مسلحة للأسقف عينة"])
    assert EMBEDDER.dims == 384 and len(v) == 384 and round(math.hypot(*v), 6) == 1.0
    assert len(emb.embed_query("عزل")) == 384


def test_batches_of_four_and_the_512_token_cap():
    s = FakeSession()
    embedder(s).embed_documents(["عزل"] * 9 + [" ".join(["خرسانة"] * 2000)])
    assert [f["input_ids"].shape[0] for f in s.feeds] == [4, 4, 2]
    assert max(f["input_ids"].shape[1] for f in s.feeds) == 512


def test_short_texts_are_batched_together_and_padded():
    s = FakeSession()
    emb = embedder(s)
    emb.embed_documents(["خرسانة مسلحة للأسقف عينة", "عزل", "عزل", "عزل", "عزل"])
    # the four short ones together, not padded to the long one: <s> passage: عزل </s>
    assert s.feeds[0]["input_ids"].shape == (4, 4)
    assert s.feeds[1]["input_ids"].shape == (1, 7)
    assert emb.embed_documents([]) == []


def test_only_the_inputs_the_model_declares():
    s = FakeSession(inputs=("input_ids", "attention_mask", "token_type_ids"))
    embedder(s).embed_query("عزل")
    feed = s.feeds[0]
    assert set(feed) == {"input_ids", "attention_mask", "token_type_ids"}
    assert (feed["token_type_ids"] == 0).all()
    assert all(feed[k].dtype == np.int64 for k in feed)

    s = FakeSession(inputs=("input_ids",))
    embedder(s).embed_query("عزل")
    assert set(s.feeds[0]) == {"input_ids"}


def test_unknown_input_is_named():
    with pytest.raises(RuntimeError, match="pixel_values"):
        embedder(FakeSession(inputs=("pixel_values",)))


def test_an_output_of_another_name_is_taken():
    s = FakeSession(output="token_embeddings")
    assert embedder(s).embed_query("عزل") == pytest.approx(expected("query: عزل"))


def test_session_is_lean():
    o = session_options(3)
    assert (o.intra_op_num_threads, o.inter_op_num_threads, o.enable_cpu_mem_arena) == (3, 1, False)


def test_default_threads_leave_cores_for_the_screen(monkeypatch):
    for cpus, threads in [(16, 4), (8, 4), (6, 3), (2, 1), (1, 1), (None, 1)]:
        monkeypatch.setattr(onnx.os, "cpu_count", lambda c=cpus: c)
        assert default_threads() == threads


def test_load_without_files_says_which(tmp_path):
    with pytest.raises(FileNotFoundError, match="tokenizer.json"):
        OnnxEmbedder.load(EMBEDDER, tmp_path)
    tiny_tokenizer().save(str(tmp_path / "tokenizer.json"))
    with pytest.raises(FileNotFoundError, match="model_quantized.onnx"):
        OnnxEmbedder.load(EMBEDDER, tmp_path)


def test_a_tokenizer_without_pad_is_refused():
    t = Tokenizer(WordLevel({"<unk>": 0, "عزل": 1}, unk_token="<unk>"))
    with pytest.raises(RuntimeError, match="<pad>"):
        OnnxEmbedder(t, FakeSession(), name="x", dims=8)


def test_only_onnx_py_imports_the_model_runtime():
    """onnxruntime and tokenizers are imported only in meaning/onnx.py, and no product module
    imports meaning/onnx.py at module level (the loader imports it inside a function)."""
    root = Path(__file__).resolve().parents[1] / "qsone"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:  # module level only
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [f"{node.module}.{a.name}" for a in node.names]
            for name in names:
                top = name.split(".")[0]
                if path.name != "onnx.py" or path.parent.name != "meaning":
                    assert top not in ("onnxruntime", "tokenizers"), path
                    assert name != "qsone.meaning.onnx", path
