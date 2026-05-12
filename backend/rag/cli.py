"""
rag/cli.py

Lightweight CLI entry point for ingesting/re-indexing the company document
corpus into the Chroma vector store. Run from the backend root::

    python -m rag.cli --reindex

Without flags it performs an incremental ingest (delegates to
``rag.ingest.ingest_all_documents``).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

from rag import ingest as ingest_module


def _reindex():
    target = ingest_module.CHROMA_PATH
    if os.path.isdir(target):
        print(f"🧹 Removing existing index: {target}")
        shutil.rmtree(target, ignore_errors=True)
    ingest_module.ingest_all_documents()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RAG ingestion CLI")
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Drop the current Chroma index and rebuild from PDFs.",
    )
    parser.add_argument(
        "--data-folder",
        default=ingest_module.DATA_FOLDER,
        help=f"Override DATA_FOLDER (default: {ingest_module.DATA_FOLDER})",
    )
    args = parser.parse_args(argv)

    # Allow CLI override of folder.
    ingest_module.DATA_FOLDER = args.data_folder

    if args.reindex:
        _reindex()
    else:
        ingest_module.ingest_all_documents()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
