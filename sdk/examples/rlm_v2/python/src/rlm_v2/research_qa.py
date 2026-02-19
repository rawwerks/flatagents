"""Research-corpus QA tooling on top of RLM v2.

Modes:
1) native (default): load corpus manifest (paths + metadata) into REPL context and let RLM read files on demand.
2) retrieval: BM25 prefilter to a candidate subset (with body text), then run RLM over that subset.

Both modes emit a deterministic verification payload (paths + quotes + doc ids).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .main import run_rlm_v2


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


@dataclass
class IndexedDoc:
    path: str
    year: int | None
    title: str
    arxiv_id: str
    tags: str
    body: str


@dataclass
class RetrievalHit:
    rank: int
    score: float
    path: str
    year: int | None
    title: str
    arxiv_id: str
    snippet: str


@dataclass
class RetrievedDoc:
    rank: int
    score: float
    path: str
    year: int | None
    title: str
    arxiv_id: str
    snippet: str
    body: str


def _extract_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---\n", 4)
    if end == -1:
        return "", text
    return text[4:end], text[end + 5 :]


def _extract_scalar(front: str, key: str) -> str:
    m = re.search(rf"(?m)^{re.escape(key)}:\s*(.+)$", front)
    return m.group(1).strip().strip("'\"") if m else ""


def _extract_tags(front: str) -> str:
    inline = re.search(r"(?m)^tags:\s*\[(.*)\]\s*$", front)
    if inline:
        raw = inline.group(1)
        items = [x.strip().strip("'\"") for x in raw.split(",") if x.strip()]
        return ", ".join(items)

    block = re.search(r"(?ms)^tags:\s*\n((?:\s*-\s*.+\n?)*)", front)
    if not block:
        return ""

    items = []
    for line in block.group(1).splitlines():
        m = re.match(r"^\s*-\s*(.+)$", line)
        if m:
            items.append(m.group(1).strip().strip("'\""))
    return ", ".join(items)


def _guess_year_from_path(path: Path) -> int | None:
    m = re.search(r"(?:_|/)(20\d{2})(?:$|[_/])", str(path.parent))
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def parse_markdown(path: Path, *, max_body_chars: int | None = None) -> IndexedDoc:
    text = path.read_text(encoding="utf-8", errors="ignore")
    front, body = _extract_frontmatter(text)

    title = _extract_scalar(front, "title")
    arxiv_id = _extract_scalar(front, "arxiv_id")
    tags = _extract_tags(front)

    if not title:
        m = re.search(r"(?m)^#\s+(.+)$", body)
        title = m.group(1).strip() if m else path.stem

    body = body.strip()
    if max_body_chars and max_body_chars > 0 and len(body) > max_body_chars:
        body = body[:max_body_chars]

    return IndexedDoc(
        path=str(path),
        year=_guess_year_from_path(path),
        title=title,
        arxiv_id=arxiv_id,
        tags=tags,
        body=body,
    )


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS docs (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            year INTEGER,
            title TEXT,
            arxiv_id TEXT,
            tags TEXT,
            body TEXT,
            mtime REAL
        )
        """
    )

    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts
        USING fts5(
            title,
            arxiv_id,
            tags,
            body,
            content='docs',
            content_rowid='id',
            tokenize='unicode61'
        )
        """
    )


def _iter_markdown_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        files.extend(sorted(root.rglob("*.md")))
    return files


def rebuild_index(db_path: Path, roots: list[Path], *, max_body_chars: int | None = None) -> dict[str, int]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_schema(conn)

        conn.execute("DELETE FROM docs_fts")
        conn.execute("DELETE FROM docs")

        files = _iter_markdown_files(roots)
        inserted = 0
        skipped = 0

        for path in files:
            try:
                doc = parse_markdown(path, max_body_chars=max_body_chars)
                stat = path.stat()
            except Exception:
                skipped += 1
                continue

            cur = conn.execute(
                """
                INSERT INTO docs(path, year, title, arxiv_id, tags, body, mtime)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (doc.path, doc.year, doc.title, doc.arxiv_id, doc.tags, doc.body, stat.st_mtime),
            )
            row_id = cur.lastrowid
            conn.execute(
                """
                INSERT INTO docs_fts(rowid, title, arxiv_id, tags, body)
                VALUES (?, ?, ?, ?, ?)
                """,
                (row_id, doc.title, doc.arxiv_id, doc.tags, doc.body),
            )
            inserted += 1

        conn.commit()
        return {"indexed": inserted, "skipped": skipped, "total_files": len(files)}
    finally:
        conn.close()


def _fts_query_from_question(question: str, *, max_terms: int = 14) -> str:
    terms = [
        t
        for t in re.findall(r"[A-Za-z0-9_]{3,}", question.lower())
        if t not in STOPWORDS
    ]
    if not terms:
        return "research"

    uniq: list[str] = []
    seen = set()
    for t in terms:
        if t in seen:
            continue
        uniq.append(t)
        seen.add(t)
        if len(uniq) >= max_terms:
            break

    return " OR ".join(uniq)


def retrieve(db_path: Path, question: str, *, top_k: int = 40) -> list[RetrievalHit]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        q = _fts_query_from_question(question)
        rows = conn.execute(
            """
            SELECT
                d.path,
                d.year,
                d.title,
                d.arxiv_id,
                bm25(docs_fts, 2.5, 1.0, 0.7, 1.2) AS score,
                snippet(docs_fts, 3, '[', ']', ' ... ', 60) AS snip
            FROM docs_fts
            JOIN docs d ON d.id = docs_fts.rowid
            WHERE docs_fts MATCH ?
            ORDER BY score
            LIMIT ?
            """,
            (q, top_k),
        ).fetchall()

        hits: list[RetrievalHit] = []
        for i, row in enumerate(rows, start=1):
            hits.append(
                RetrievalHit(
                    rank=i,
                    score=float(row["score"]) if row["score"] is not None else 0.0,
                    path=str(row["path"]),
                    year=int(row["year"]) if row["year"] is not None else None,
                    title=str(row["title"] or ""),
                    arxiv_id=str(row["arxiv_id"] or ""),
                    snippet=str(row["snip"] or ""),
                )
            )
        return hits
    finally:
        conn.close()


def list_corpus_docs(
    db_path: Path,
    *,
    max_docs: int = 0,
    max_doc_chars: int | None = None,
    include_body: bool = False,
) -> list[RetrievedDoc]:
    """Load corpus docs for RLM-native mode.

    By default this returns a lightweight manifest (paths + metadata, no body text)
    so we do not serialize the full corpus into REPL context.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if include_body:
            sql = """
                SELECT path, year, title, arxiv_id, body
                FROM docs
                ORDER BY COALESCE(year, 0) DESC, path ASC
            """
        else:
            sql = """
                SELECT path, year, title, arxiv_id
                FROM docs
                ORDER BY COALESCE(year, 0) DESC, path ASC
            """
        rows = conn.execute(sql).fetchall()

        docs: list[RetrievedDoc] = []
        for i, row in enumerate(rows, start=1):
            body = ""
            if include_body:
                body = str(row["body"] or "")
                if max_doc_chars and max_doc_chars > 0 and len(body) > max_doc_chars:
                    body = body[:max_doc_chars]

            snippet = body[:240].replace("\n", " ").strip() if body else ""

            docs.append(
                RetrievedDoc(
                    rank=i,
                    score=0.0,
                    path=str(row["path"]),
                    year=int(row["year"]) if row["year"] is not None else None,
                    title=str(row["title"] or ""),
                    arxiv_id=str(row["arxiv_id"] or ""),
                    snippet=snippet,
                    body=body,
                )
            )

        if max_docs and max_docs > 0:
            return docs[:max_docs]
        return docs
    finally:
        conn.close()


def hydrate_docs(db_path: Path, hits: list[RetrievalHit], *, max_doc_chars: int | None = None) -> list[RetrievedDoc]:
    if not hits:
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        path_to_body: dict[str, str] = {}
        for hit in hits:
            row = conn.execute("SELECT body FROM docs WHERE path = ?", (hit.path,)).fetchone()
            body = str(row["body"] or "") if row else ""
            if max_doc_chars and max_doc_chars > 0 and len(body) > max_doc_chars:
                body = body[:max_doc_chars]
            path_to_body[hit.path] = body

        out: list[RetrievedDoc] = []
        for hit in hits:
            out.append(
                RetrievedDoc(
                    rank=hit.rank,
                    score=hit.score,
                    path=hit.path,
                    year=hit.year,
                    title=hit.title,
                    arxiv_id=hit.arxiv_id,
                    snippet=hit.snippet,
                    body=path_to_body.get(hit.path, ""),
                )
            )
        return out
    finally:
        conn.close()


def build_retrieval_context(
    docs: list[RetrievedDoc],
    *,
    max_docs: int = 0,
    include_retrieval_score: bool = True,
    include_snippet: bool = True,
    include_body: bool = True,
) -> str:
    selected = docs
    if max_docs and max_docs > 0:
        selected = docs[:max_docs]

    chunks: list[str] = []
    for doc in selected:
        lines = [
            f"### DOC {doc.rank}",
            f"path: {doc.path}",
            f"year: {doc.year if doc.year is not None else ''}",
            f"arxiv_id: {doc.arxiv_id}",
            f"title: {doc.title}",
        ]
        if include_retrieval_score:
            lines.append(f"retrieval_score: {doc.score:.4f}")
        if include_snippet:
            lines.extend(
                [
                    "snippet:",
                    doc.snippet,
                ]
            )
        if include_body:
            lines.extend(
                [
                    "body:",
                    doc.body,
                ]
            )
        chunks.append("\n".join(lines))

    return "\n\n".join(chunks)


def _research_task(question: str, *, mode: Literal["native", "retrieval"], doc_count: int) -> str:
    if mode == "native":
        context_note = (
            "`context` contains a corpus manifest (DOC ids + file paths + metadata), not full file contents. "
            "Use targeted Python file reads (open/pathlib) for specific candidate files; do not load the whole corpus. "
        )
    else:
        context_note = "`context` contains retrieved candidate documents with snippets and bodies. "

    return (
        "You are inside a recursive REPL loop. "
        "Use symbolic operations over `context` (search/slice/chunk) and use `llm_query(...)` "
        "for focused semantic checks on candidate excerpts. "
        "Avoid printing full context; build state in variables across iterations. "
        "Set `Final` only when answer + evidence are complete. "
        f"{context_note}"
        f"Doc count in context: {doc_count}.\n\n"
        "Return Final as markdown with EXACT sections and format:\n"
        "# ANSWER\n"
        "<short answer>\n\n"
        "# EVIDENCE\n"
        "- DOC: <number>\n"
        "  QUOTE: <verbatim quote from that doc body>\n"
        "  WHY: <why quote supports answer>\n"
        "(repeat evidence blocks as needed)\n\n"
        "# CONFIDENCE\n"
        "<number 0..1>\n\n"
        "# GAPS\n"
        "<what is uncertain or missing>\n"
        "Do not invent citations; DOC number must exist in context."
        f"\n\nQuestion: {question}"
    )


def parse_evidence_blocks(answer_text: str) -> list[dict[str, Any]]:
    text = "" if answer_text is None else str(answer_text)
    pattern = re.compile(
        r"-\s*DOC:\s*(\d+)\s*\n\s*QUOTE:\s*(.+?)\s*\n\s*WHY:\s*(.+?)(?=\n\s*-\s*DOC:|\n\s*#\s|\Z)",
        re.DOTALL,
    )

    blocks: list[dict[str, Any]] = []
    for m in pattern.finditer(text):
        blocks.append(
            {
                "doc_id": int(m.group(1)),
                "quote": m.group(2).strip(),
                "why": m.group(3).strip(),
            }
        )
    return blocks


def parse_confidence(answer_text: str) -> float | None:
    text = "" if answer_text is None else str(answer_text)
    m = re.search(r"(?ms)^#\s*CONFIDENCE\s*\n\s*([0-9]*\.?[0-9]+)", text)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    if val < 0.0:
        return 0.0
    if val > 1.0:
        return 1.0
    return val


def build_verification_payload(
    *,
    question: str,
    answer_text: str,
    hits: list[RetrievalHit],
) -> dict[str, Any]:
    by_rank = {h.rank: h for h in hits}
    parsed = parse_evidence_blocks(answer_text)

    citations: list[dict[str, Any]] = []
    invalid_doc_ids: list[int] = []

    for item in parsed:
        doc_id = int(item["doc_id"])
        hit = by_rank.get(doc_id)
        if hit is None:
            invalid_doc_ids.append(doc_id)
            continue

        citations.append(
            {
                "doc_id": doc_id,
                "path": hit.path,
                "title": hit.title,
                "arxiv_id": hit.arxiv_id,
                "year": hit.year,
                "retrieval_score": hit.score,
                "quote": item["quote"],
                "why": item["why"],
            }
        )

    payload = {
        "question": question,
        "answer_text": "" if answer_text is None else str(answer_text),
        "confidence": parse_confidence(answer_text),
        "citation_count": len(citations),
        "citations": citations,
        "invalid_doc_ids": invalid_doc_ids,
        "top_hits": [h.__dict__ for h in hits[:10]],
    }
    return payload


def _hits_from_docs(docs: list[RetrievedDoc]) -> list[RetrievalHit]:
    out: list[RetrievalHit] = []
    for doc in docs:
        out.append(
            RetrievalHit(
                rank=doc.rank,
                score=doc.score,
                path=doc.path,
                year=doc.year,
                title=doc.title,
                arxiv_id=doc.arxiv_id,
                snippet=doc.snippet,
            )
        )
    return out


async def ask_with_rlm(
    *,
    db_path: Path,
    question: str,
    mode: Literal["native", "retrieval"],
    top_k: int,
    max_docs: int,
    max_doc_chars: int | None,
    max_depth: int,
    timeout_seconds: int,
    max_iterations: int,
    max_steps: int,
    inspect: bool,
    inspect_level: str,
    trace_dir: str,
    print_iterations: bool,
) -> dict[str, Any]:
    docs: list[RetrievedDoc]
    hits: list[RetrievalHit]

    if mode == "retrieval":
        hits = retrieve(db_path, question, top_k=top_k)
        if not hits:
            return {
                "answer": "No matching papers found in index.",
                "reason": "empty_retrieval",
                "mode": mode,
                "retrieval_hits": [],
                "verification": {
                    "question": question,
                    "answer_text": "No matching papers found in index.",
                    "citation_count": 0,
                    "citations": [],
                    "invalid_doc_ids": [],
                    "top_hits": [],
                    "confidence": None,
                },
            }

        docs = hydrate_docs(db_path, hits, max_doc_chars=max_doc_chars)
        context = build_retrieval_context(
            docs,
            max_docs=max_docs,
            include_retrieval_score=True,
            include_snippet=True,
            include_body=True,
        )
    else:
        docs = list_corpus_docs(db_path, max_docs=max_docs, max_doc_chars=max_doc_chars, include_body=False)
        if not docs:
            return {
                "answer": "No papers found in index.",
                "reason": "empty_corpus",
                "mode": mode,
                "retrieval_hits": [],
                "verification": {
                    "question": question,
                    "answer_text": "No papers found in index.",
                    "citation_count": 0,
                    "citations": [],
                    "invalid_doc_ids": [],
                    "top_hits": [],
                    "confidence": None,
                },
            }

        hits = _hits_from_docs(docs)
        context = build_retrieval_context(
            docs,
            max_docs=max_docs,
            include_retrieval_score=False,
            include_snippet=False,
            include_body=False,
        )

    task = _research_task(question, mode=mode, doc_count=len(docs))

    result = await run_rlm_v2(
        task=task,
        long_context=context,
        max_depth=max_depth,
        timeout_seconds=timeout_seconds,
        max_iterations=max_iterations,
        max_steps=max_steps,
        inspect=inspect,
        inspect_level=inspect_level,
        trace_dir=trace_dir,
        print_iterations=print_iterations,
    )

    answer_text = "" if result.get("answer") is None else str(result.get("answer"))
    result["mode"] = mode
    result["retrieval_hits"] = [h.__dict__ for h in hits]
    result["verification"] = build_verification_payload(
        question=question,
        answer_text=answer_text,
        hits=hits,
    )
    return result


def _default_roots() -> list[Path]:
    home = Path.home()
    return [
        home / "code" / "analysis" / "ml_research_analysis_2023",
        home / "code" / "analysis" / "ml_research_analysis_2024",
        home / "code" / "analysis" / "ml_research_analysis_2025",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Research corpus QA with RLM v2 (RLM-native or retrieval mode)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Build or rebuild local SQLite FTS index")
    p_index.add_argument("--db", default="./research_index.db", help="Path to SQLite DB")
    p_index.add_argument(
        "--root",
        action="append",
        default=[],
        help="Root directory to index (.md files). Can be repeated.",
    )
    p_index.add_argument(
        "--max-body-chars",
        type=int,
        default=0,
        help="Max chars per doc body at index time (0 = keep full body).",
    )

    p_ask = sub.add_parser("ask", help="Ask a question over indexed corpus with RLM")
    p_ask.add_argument("--db", default="./research_index.db", help="Path to SQLite DB")
    p_ask.add_argument("--question", "-q", required=True)
    p_ask.add_argument(
        "--mode",
        choices=["native", "retrieval"],
        default="native",
        help="native=paths+metadata manifest (RLM reads files on demand); retrieval=BM25 prefilter with body text.",
    )
    p_ask.add_argument("--top-k", type=int, default=60, help="Retrieval mode only.")
    p_ask.add_argument(
        "--max-docs",
        type=int,
        default=0,
        help="Max docs loaded into RLM context (0 = all docs in selected mode).",
    )
    p_ask.add_argument(
        "--max-doc-chars",
        type=int,
        default=0,
        help="Max chars per doc in ask mode (0 = no truncation).",
    )
    p_ask.add_argument("--dry-run", action="store_true", help="Only print selected docs; skip RLM")

    p_ask.add_argument("--max-depth", type=int, default=5)
    p_ask.add_argument("--timeout-seconds", type=int, default=300)
    p_ask.add_argument("--max-iterations", type=int, default=20)
    p_ask.add_argument("--max-steps", type=int, default=80)
    p_ask.add_argument("--inspect", action="store_true")
    p_ask.add_argument("--inspect-level", choices=["summary", "full"], default="summary")
    p_ask.add_argument("--trace-dir", default="./traces")
    p_ask.add_argument("--print-iterations", action="store_true")
    p_ask.add_argument("--save-retrieval", default="", help="Optional path to save retrieval hits JSON")
    p_ask.add_argument("--save-verification", default="", help="Optional path to save verification JSON")

    args = parser.parse_args()

    if args.command == "index":
        roots = [Path(p).expanduser() for p in (args.root or [])]
        if not roots:
            roots = _default_roots()

        stats = rebuild_index(Path(args.db).expanduser(), roots, max_body_chars=args.max_body_chars)
        print(json.dumps({"db": str(Path(args.db).expanduser()), "roots": [str(r) for r in roots], **stats}, indent=2))
        return

    if args.command == "ask":
        db_path = Path(args.db).expanduser()
        if not db_path.exists():
            raise FileNotFoundError(f"Index DB not found: {db_path}. Run `index` first.")

        max_doc_chars = args.max_doc_chars if args.max_doc_chars > 0 else None

        if args.mode == "retrieval":
            hits = retrieve(db_path, args.question, top_k=args.top_k)
            print(f"Retrieved {len(hits)} hits (retrieval mode)")
            for h in hits[: min(10, len(hits))]:
                print(f"[{h.rank}] score={h.score:.4f} | {h.title} | {h.path}")
            selected_hits = hits
        else:
            docs = list_corpus_docs(
                db_path,
                max_docs=args.max_docs,
                max_doc_chars=max_doc_chars,
                include_body=False,
            )
            print(f"Loaded {len(docs)} docs (native mode)")
            selected_hits = _hits_from_docs(docs)
            for h in selected_hits[: min(10, len(selected_hits))]:
                print(f"[{h.rank}] {h.title} | {h.path}")

        if args.save_retrieval:
            out = Path(args.save_retrieval).expanduser()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps([h.__dict__ for h in selected_hits], indent=2), encoding="utf-8")
            print(f"Saved selected docs: {out}")

        if args.dry_run:
            return

        result = asyncio.run(
            ask_with_rlm(
                db_path=db_path,
                question=args.question,
                mode=args.mode,
                top_k=args.top_k,
                max_docs=args.max_docs,
                max_doc_chars=max_doc_chars,
                max_depth=args.max_depth,
                timeout_seconds=args.timeout_seconds,
                max_iterations=args.max_iterations,
                max_steps=args.max_steps,
                inspect=args.inspect,
                inspect_level=args.inspect_level,
                trace_dir=args.trace_dir,
                print_iterations=args.print_iterations,
            )
        )

        print("\nAnswer")
        print("-" * 72)
        print(result.get("answer"))
        print("Mode:", result.get("mode"))
        print("Reason:", result.get("reason"))
        verification = result.get("verification") or {}
        print("Citations:", verification.get("citation_count", 0))
        print("Confidence:", verification.get("confidence"))
        if result.get("trace_path"):
            print("Trace:", result.get("trace_path"))

        if args.save_verification:
            out = Path(args.save_verification).expanduser()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(verification, indent=2), encoding="utf-8")
            print(f"Saved verification payload: {out}")
        return


if __name__ == "__main__":
    main()
