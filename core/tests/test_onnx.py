"""The search models on onnxruntime, with a fake session and a tiny tokenizer: no model file."""

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
from qsone.meaning.onnx import OnnxEmbedder, OnnxReranker, default_threads, session_options  # noqa: E402

WORDS = ["خرسانة", "مسلحة", "للأسقف", "عينة", "عزل", "steel", "bars", "sample", "حديد", "تسليح"]
SPECIAL = ["<s>", "<pad>", "</s>", "<unk>"]
VOCAB = {w: i for i, w in enumerate(SPECIAL + WORDS)}


def tiny_tokenizer() -> Tokenizer:
    t = Tokenizer(WordLevel(VOCAB, unk_token="<unk>"))
    t.pre_tokenizer = WhitespaceSplit()
    t.post_processor = TemplateProcessing(
        single="<s> $A </s>",
        pair="<s> $A </s> </s> $B </s>",
        special_tokens=[("<s>", VOCAB["<s>"]), ("</s>", VOCAB["</s>"])],
    )
    return t


class _Arg:
    def __init__(self, name):
        self.name = name


class FakeSession:
    """Declares its inputs, records every feed, and answers like the model would.

    As an embedder, each row's CLS vector encodes the first real token id (not normalised).
    As a reranker, each pair's logit is the number of real tokens in it."""

    def __init__(self, dims=None, inputs=("input_ids", "attention_mask"), logits=False):
        self.dims, self.inputs, self.logits, self.feeds = dims, inputs, logits, []

    def get_inputs(self):
        return [_Arg(n) for n in self.inputs]

    def get_outputs(self):
        return [_Arg("logits" if self.logits else "last_hidden_state")]

    def run(self, names, feed):
        self.feeds.append(feed)
        ids = feed["input_ids"]
        if self.logits:
            return [feed["attention_mask"].sum(axis=1, keepdims=True).astype(np.float32)]
        b, t = ids.shape
        out = np.full((b, t, self.dims), 0.5, dtype=np.float32)
        for row in range(b):
            first = int(ids[row, 1])
            out[row, 0] = 0.0
            out[row, 0, first % self.dims] = 3.0
            out[row, 0, (first * 3 + 1) % self.dims] += 4.0
        return [out]


def test_cls_row_normalised_and_back_in_input_order():
    emb = OnnxEmbedder(tiny_tokenizer(), FakeSession(dims=8), name="x", dims=8)
    texts = ["خرسانة مسلحة للأسقف عينة", "عزل", "steel bars sample"]
    out = emb.embed_documents(texts)
    assert [round(math.hypot(*v), 6) for v in out] == [1.0, 1.0, 1.0]
    assert out == [emb.embed_query(t) for t in texts]
    assert len({tuple(v) for v in out}) == 3


def test_batches_of_four_and_the_512_token_cap():
    s = FakeSession(dims=8)
    emb = OnnxEmbedder(tiny_tokenizer(), s, name="x", dims=8)
    emb.embed_documents(["عزل"] * 9 + [" ".join(["خرسانة"] * 2000)])
    assert [f["input_ids"].shape[0] for f in s.feeds] == [4, 4, 2]
    assert max(f["input_ids"].shape[1] for f in s.feeds) == 512


def test_short_texts_are_batched_together_and_padded():
    s = FakeSession(dims=8)
    emb = OnnxEmbedder(tiny_tokenizer(), s, name="x", dims=8)
    emb.embed_documents(["خرسانة مسلحة للأسقف عينة", "عزل", "عزل", "عزل", "عزل"])
    # the four short ones together, not padded to the long one
    assert s.feeds[0]["input_ids"].shape == (4, 3)
    assert s.feeds[1]["input_ids"].shape == (1, 6)
    assert emb.embed_documents([]) == []


def test_only_the_inputs_the_model_declares():
    s = FakeSession(dims=8, inputs=("input_ids", "attention_mask", "token_type_ids"))
    OnnxEmbedder(tiny_tokenizer(), s, name="x", dims=8).embed_query("عزل")
    feed = s.feeds[0]
    assert set(feed) == {"input_ids", "attention_mask", "token_type_ids"}
    assert (feed["token_type_ids"] == 0).all()
    assert all(feed[k].dtype == np.int64 for k in feed)

    s = FakeSession(dims=8, inputs=("input_ids",))
    OnnxEmbedder(tiny_tokenizer(), s, name="x", dims=8).embed_query("عزل")
    assert set(s.feeds[0]) == {"input_ids"}


def test_unknown_input_is_named():
    with pytest.raises(RuntimeError, match="pixel_values"):
        session = FakeSession(dims=8, inputs=("pixel_values",))
        OnnxEmbedder(tiny_tokenizer(), session, name="x", dims=8)
    with pytest.raises(RuntimeError, match="pixel_values"):
        OnnxReranker(tiny_tokenizer(), FakeSession(logits=True, inputs=("pixel_values",)), name="x")


def test_reranker_scores_pairs_in_order():
    s = FakeSession(logits=True)
    rr = OnnxReranker(tiny_tokenizer(), s, name="x")
    texts = ["steel bars sample", "عزل", "خرسانة مسلحة للأسقف عينة", "حديد تسليح", "عينة"]
    scores = rr.rerank("حديد", texts)
    # <s> q </s> </s> text </s>: 5 tokens around the text's own
    assert scores == [8.0, 6.0, 9.0, 7.0, 6.0]
    assert all(isinstance(x, float) for x in scores)
    assert [f["input_ids"].shape[0] for f in s.feeds] == [4, 1]
    row = s.feeds[1]["input_ids"][0].tolist()
    assert row == [VOCAB[w] for w in ["<s>", "حديد", "</s>", "</s>", "عينة", "</s>"]]
    assert rr.rerank("حديد", []) == []


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
    with pytest.raises(FileNotFoundError, match="model_int8.onnx"):
        OnnxEmbedder.load(EMBEDDER, tmp_path)


def test_a_tokenizer_without_pad_is_refused():
    t = Tokenizer(WordLevel({"<unk>": 0, "عزل": 1}, unk_token="<unk>"))
    with pytest.raises(RuntimeError, match="<pad>"):
        OnnxEmbedder(t, FakeSession(dims=8), name="x", dims=8)


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
