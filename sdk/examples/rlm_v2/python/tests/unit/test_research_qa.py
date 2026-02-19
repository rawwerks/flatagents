from __future__ import annotations

from pathlib import Path

from rlm_v2 import research_qa


def test_parse_markdown_extracts_frontmatter_fields(tmp_path: Path) -> None:
    p = tmp_path / "doc.md"
    p.write_text(
        """---
title: Example Paper
arxiv_id: '2501.00001'
tags:
  - llm
  - retrieval
---

# Example Paper

This is the body.
""",
        encoding="utf-8",
    )

    doc = research_qa.parse_markdown(p)

    assert doc.title == "Example Paper"
    assert doc.arxiv_id == "2501.00001"
    assert "llm" in doc.tags
    assert "This is the body." in doc.body


def test_fts_query_builder_is_nonempty() -> None:
    q = research_qa._fts_query_from_question(
        "What are the best methods for retrieval-augmented generation in vision-language models?"
    )
    assert q
    assert "OR" in q


def test_rebuild_retrieve_and_hydrate_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()

    (root / "a.md").write_text(
        """---
title: Sparse Retrieval for QA
arxiv_id: '2501.10001'
---

Sparse retrieval and BM25 can be strong lexical baselines.
""",
        encoding="utf-8",
    )

    (root / "b.md").write_text(
        """---
title: Vision LoRA for Multimodal Models
arxiv_id: '2502.20002'
---

LoRA adapters can inject visual features into language models.
""",
        encoding="utf-8",
    )

    db = tmp_path / "idx.db"
    stats = research_qa.rebuild_index(db, [root])
    assert stats["indexed"] == 2

    hits = research_qa.retrieve(db, "lora multimodal vision", top_k=5)
    assert hits
    assert hits[0].title

    docs = research_qa.hydrate_docs(db, hits, max_doc_chars=500)
    assert docs
    assert docs[0].body


def test_build_retrieval_context_contains_paths_and_bodies() -> None:
    docs = [
        research_qa.RetrievedDoc(
            rank=1,
            score=1.23,
            path="/tmp/a.md",
            year=2025,
            title="A",
            arxiv_id="2501.1",
            snippet="snippet A",
            body="body A",
        ),
        research_qa.RetrievedDoc(
            rank=2,
            score=1.24,
            path="/tmp/b.md",
            year=2024,
            title="B",
            arxiv_id="2502.2",
            snippet="snippet B",
            body="body B",
        ),
    ]

    context = research_qa.build_retrieval_context(docs, max_docs=2)
    assert "### DOC 1" in context
    assert "path: /tmp/a.md" in context
    assert "snippet B" in context
    assert "body B" in context


def test_parse_evidence_and_verification_payload() -> None:
    answer = """# ANSWER
Vision-LoRA is a strong PEFT path.

# EVIDENCE
- DOC: 1
  QUOTE: Vision as LoRA (VoRA) introduces a new paradigm.
  WHY: Directly states the core contribution.

# CONFIDENCE
0.78

# GAPS
Need broader benchmark comparison.
"""

    hits = [
        research_qa.RetrievalHit(
            rank=1,
            score=0.1,
            path="/tmp/a.md",
            year=2025,
            title="Vision as LoRA",
            arxiv_id="2503.20680",
            snippet="...",
        )
    ]

    payload = research_qa.build_verification_payload(
        question="What is Vision as LoRA?",
        answer_text=answer,
        hits=hits,
    )

    assert payload["citation_count"] == 1
    assert payload["citations"][0]["doc_id"] == 1
    assert payload["citations"][0]["path"] == "/tmp/a.md"
    assert payload["confidence"] == 0.78


def test_list_corpus_docs_loads_manifest_by_default(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()

    (root / "a.md").write_text("# A\n\nBody A", encoding="utf-8")
    (root / "b.md").write_text("# B\n\nBody B", encoding="utf-8")

    db = tmp_path / "idx.db"
    research_qa.rebuild_index(db, [root])

    docs = research_qa.list_corpus_docs(db)
    assert len(docs) == 2
    assert docs[0].rank == 1
    assert docs[0].body == ""


def test_list_corpus_docs_include_body_loads_text(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()

    (root / "a.md").write_text("# A\n\nBody A", encoding="utf-8")

    db = tmp_path / "idx.db"
    research_qa.rebuild_index(db, [root])

    docs = research_qa.list_corpus_docs(db, include_body=True)
    assert len(docs) == 1
    assert "Body A" in docs[0].body


def test_build_retrieval_context_native_omits_retrieval_score_and_body() -> None:
    docs = [
        research_qa.RetrievedDoc(
            rank=1,
            score=0.0,
            path="/tmp/a.md",
            year=2025,
            title="A",
            arxiv_id="2501.1",
            snippet="snippet",
            body="body",
        )
    ]

    context = research_qa.build_retrieval_context(
        docs,
        include_retrieval_score=False,
        include_snippet=False,
        include_body=False,
    )
    assert "### DOC 1" in context
    assert "retrieval_score:" not in context
    assert "body:" not in context
    assert "snippet:" not in context
