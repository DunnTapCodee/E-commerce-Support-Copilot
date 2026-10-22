"""Knowledge base ingestion: read policies.json, chunking, and tag version & is_active."""
import json
from pathlib import Path
from typing import List

from contracts.schemas import RetrievedDocument


def load_policy_documents(policy_file_path: Path) -> List[RetrievedDocument]:
    """Load policy documents from policies.json file."""
    if not policy_file_path.exists():
        raise FileNotFoundError(f"Policies file not found at: {policy_file_path}")

    with open(policy_file_path, "r", encoding="utf-8") as f:
        raw_items = json.load(f)

    documents: List[RetrievedDocument] = []
    for item in raw_items:
        documents.append(
            RetrievedDocument(
                doc_id=item["doc_id"],
                title=item["title"],
                content=item["content"],
                version=str(item.get("version", "1.0")),
                is_active=bool(item.get("is_active", True)),
                effective_date=item.get("effective_date"),
                expiration_date=item.get("expiration_date"),
                score=1.0,
            )
        )
    return documents
