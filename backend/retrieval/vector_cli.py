"""Rebuild the versioned external guideline Qdrant index from CP-006 artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .vector import (
    DEFAULT_COLLECTION_NAME,
    DeterministicHashEmbeddingModel,
    FastEmbedMultilingualModel,
    rebuild_qdrant_local,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild the CarePath external evidence index.")
    parser.add_argument(
        "--chunks",
        type=Path,
        default=Path("data/guidelines/generated/chunks.jsonl"),
        help="CP-006 chunks.jsonl path.",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("data/guidelines/sources.yaml"),
        help="CP-006 source registry path.",
    )
    parser.add_argument(
        "--qdrant-path",
        type=Path,
        default=Path("data/guidelines/qdrant"),
        help="Qdrant Local persistence directory.",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION_NAME,
        help="Versioned Qdrant collection name.",
    )
    parser.add_argument(
        "--embedding-model",
        default=None,
        help="FastEmbed multilingual model name. Defaults to the CarePath configured model.",
    )
    parser.add_argument(
        "--embedding-backend",
        choices=("fastembed", "hash-test"),
        default="fastembed",
        help="Use fastembed for real indexing; hash-test exists only for deterministic tests.",
    )
    args = parser.parse_args()

    embedder = (
        DeterministicHashEmbeddingModel()
        if args.embedding_backend == "hash-test"
        else FastEmbedMultilingualModel(model_name=args.embedding_model)
        if args.embedding_model
        else FastEmbedMultilingualModel()
    )
    report = rebuild_qdrant_local(
        chunks_path=args.chunks,
        registry_path=args.registry,
        qdrant_path=args.qdrant_path,
        collection_name=args.collection,
        embedder=embedder,
    )
    print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
