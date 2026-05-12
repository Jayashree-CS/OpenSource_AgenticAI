"""
RAG ingestion pipeline for company documents.

This script re-ingests every PDF under ``./data/`` into the persisted Chroma
vector store at ``./chroma_db/hr_policies``.

Key design points:

1. **Local embeddings** (``HuggingFaceEmbeddings``) so the ingestion matches
   the retriever exactly (``rag/retriever.py``). No HF API token required,
   no silent remote failures.

2. **Every chunk is tagged with metadata** so the RBAC filter in
   ``retriever.py`` actually returns results for non-admin users:

   - ``source``:        filename, shown as citation in answers.
   - ``access_level``:  one of ``employee`` / ``manager`` / ``admin``.
     Default is ``employee`` (readable by everyone). Documents whose
     filename contains ``manager`` / ``leadership`` are tagged ``manager``.
     Files containing ``admin`` / ``confidential`` / ``compensation`` are
     tagged ``admin``.
   - ``category``:      coarse topic for future facet filtering
     (``leave`` / ``salary`` / ``code`` / ``csr`` / ``handbook`` / ``policy``).

3. **Idempotent re-ingest**: the existing collection is cleared before
   re-ingest so re-running never duplicates chunks.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter


load_dotenv()


# ---------------------------------------------------------------------------
# Config — kept aligned with rag/retriever.py
# ---------------------------------------------------------------------------

DATA_FOLDER = os.getenv("RAG_DATA_FOLDER", "./data")
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db/hr_policies")
EMBED_MODEL = os.getenv("HF_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "100"))


# ---------------------------------------------------------------------------
# Metadata classifiers
# ---------------------------------------------------------------------------

_ADMIN_MARKERS = ("admin", "confidential", "compensation", "salary-advance")
_MANAGER_MARKERS = ("manager", "leadership", "approval")

_CATEGORY_MARKERS = {
    "leave":     ("leave",),
    "salary":    ("salary", "payroll", "advance", "compensation"),
    "code":      ("code", "conduct", "ethics"),
    "csr":       ("csr",),
    "handbook":  ("handbook", "company_knowledge", "novigo"),
    "policy":    ("policy",),
}


def _classify_access_level(filename: str) -> str:
    lower = filename.lower()
    if any(tag in lower for tag in _ADMIN_MARKERS):
        return "admin"
    if any(tag in lower for tag in _MANAGER_MARKERS):
        return "manager"
    return "employee"


def _classify_category(filename: str) -> str:
    lower = filename.lower()
    for category, markers in _CATEGORY_MARKERS.items():
        if any(marker in lower for marker in markers):
            return category
    return "general"


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def _load_pdfs(root_folder: str):
    docs = []
    for root, _dirs, files in os.walk(root_folder):
        for file in files:
            if not file.lower().endswith(".pdf"):
                continue
            file_path = os.path.join(root, file)
            try:
                print(f"Loading PDF: {file}")
                loader = PyPDFLoader(file_path)
                loaded_docs = loader.load()

                access_level = _classify_access_level(file)
                category = _classify_category(file)

                for doc in loaded_docs:
                    doc.metadata["source"] = file
                    doc.metadata["access_level"] = access_level
                    doc.metadata["category"] = category
                    # Ensure int page numbers don't confuse Chroma filters.
                    if "page" in doc.metadata and doc.metadata["page"] is not None:
                        doc.metadata["page"] = int(doc.metadata["page"])

                docs.extend(loaded_docs)
                print(f"  -> access_level={access_level} category={category} pages={len(loaded_docs)}")

            except Exception as exc:
                print(f"Error loading {file}: {exc}")
    return docs


def _reset_persistent_store(path: str) -> None:
    """Delete the existing Chroma directory so re-ingest never duplicates."""
    p = Path(path)
    if p.exists():
        try:
            shutil.rmtree(p)
            print(f"Cleared existing Chroma store at {p}")
        except Exception as exc:
            print(f"Warning: failed to clear {p}: {exc}")


def ingest_all_documents(reset: bool = True) -> int:
    """Ingest every PDF under DATA_FOLDER. Returns the number of chunks indexed."""
    docs = _load_pdfs(DATA_FOLDER)
    if not docs:
        print("No PDF documents found under", DATA_FOLDER)
        return 0

    print(f"\nLoaded {len(docs)} total pages")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    chunks = splitter.split_documents(docs)
    print(f"Created {len(chunks)} chunks")

    # Stable chunk IDs (file + page + chunk offset) so re-ingest is stable.
    for i, chunk in enumerate(chunks):
        src = chunk.metadata.get("source", "doc")
        page = chunk.metadata.get("page", "x")
        chunk.metadata["chunk_id"] = f"{src}#p{page}#c{i}"

    if reset:
        _reset_persistent_store(CHROMA_PATH)

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=CHROMA_PATH,
    )

    print(f"ChromaDB rebuilt at {CHROMA_PATH} with {len(chunks)} chunks")
    return len(chunks)


if __name__ == "__main__":
    ingest_all_documents()