"""Dataset Extractor & Auto-Sync Engine for Continual ML Training.
Extracts interaction data across 3 strategic formats:
1. Switched / Standalone queries (Natural language & domain slang).
2. Elliptical queries with contextual facts prefix.
3. Canonical rewritten queries.

Exports to CSV for manual review, labeling correction, and ML model retraining.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CSV_PATH = ROOT_DIR / "data" / "continual_learning_dataset.csv"


def get_db_path(db_name: str) -> Path:
    """Find DB file either in local root or docker db_storage volume."""
    local_p = ROOT_DIR / db_name
    if local_p.exists():
        return local_p
    storage_p = ROOT_DIR / "db_storage" / db_name
    if storage_p.exists():
        return storage_p
    return local_p


def extract_continual_learning_records(
    telemetry_db_path: Optional[Path] = None,
    conversations_db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Extract, deduplicate, and enrich training samples from SQLite databases."""
    t_path = telemetry_db_path or get_db_path("copilot_telemetry.sqlite3")
    c_path = conversations_db_path or get_db_path("copilot_conversations.sqlite3")

    samples: List[Dict[str, Any]] = []
    seen_keys = set()

    # 1. Read conversation sessions for context & entities
    session_context_map: Dict[str, Dict[str, Any]] = {}
    if c_path.exists():
        try:
            with sqlite3.connect(str(c_path)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT session_id, customer_id, active_intent, active_order_id, context_summary FROM conversation_sessions"
                ).fetchall()
                for r in rows:
                    session_context_map[r["session_id"]] = dict(r)
        except Exception as exc:
            print(f"[DatasetExtractor] Warning loading sessions: {exc}")

    # 2. Extract from Telemetry Logs (Human-in-the-loop approved or high-confidence LLM predictions)
    if t_path.exists():
        try:
            with sqlite3.connect(str(t_path)) as conn:
                conn.row_factory = sqlite3.Row
                # Query logs that have human approval, or have high confidence (>= 0.85) from LLM
                query = """
                SELECT interaction_id, timestamp, customer_query, predicted_intent, intent_confidence,
                       guardrail_action, raw_draft_text, human_action, final_sent_text
                FROM telemetry_logs
                WHERE predicted_intent IS NOT NULL
                  AND predicted_intent != ''
                  AND (human_action IN ('APPROVE', 'EDIT') OR intent_confidence >= 0.85)
                ORDER BY timestamp ASC;
                """
                rows = conn.execute(query).fetchall()
                for r in rows:
                    q = (r["customer_query"] or "").strip()
                    intent = r["predicted_intent"].strip()
                    if not q or not intent:
                        continue

                    # Clean query (strip newline spam if any)
                    clean_query = " ".join(q.split())
                    words = clean_query.split()
                    word_count = len(words)

                    # Determine Strategy / Source Group
                    strategy = "1_standalone"
                    training_input = clean_query

                    # Detect if elliptical short query (< 4 words)
                    is_short = word_count <= 4
                    has_domain_keyword = any(
                        k in clean_query.lower()
                        for k in [
                            "hủy", "huy", "cancel", "voucher", "mã giảm", "freeship", "giảm giá",
                            "đổi trả", "hoàn tiền", "bảo hành", "nhân viên", "người thật"
                        ]
                    )

                    if rewritten_query and rewritten_query.strip() and rewritten_query.strip() != clean_query:
                        strategy = "3_rewritten"
                        training_input = rewritten_query.strip()
                    else:
                        strategy = "1_standalone"
                        training_input = clean_query

                    dedup_key = (training_input.lower(), intent)
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    samples.append({
                        "id": r["interaction_id"],
                        "source_strategy": strategy,
                        "raw_user_query": clean_query,
                        "training_input": training_input,
                        "intent_label": intent,
                        "confidence": float(r["intent_confidence"] or 0.90),
                        "human_verified": 1 if r["human_action"] in ("APPROVE", "EDIT") else 0,
                        "human_action": r["human_action"] or "AUTO_LLM",
                        "created_at": r["timestamp"] or "",
                    })
        except Exception as exc:
            print(f"[DatasetExtractor] Warning loading telemetry: {exc}")

    return samples


def export_dataset_to_csv(
    output_path: Optional[Path] = None,
    telemetry_db_path: Optional[Path] = None,
    conversations_db_path: Optional[Path] = None,
) -> Path:
    """Extract and write dataset to CSV file with standard columns."""
    out_file = output_path or DEFAULT_CSV_PATH
    out_file.parent.mkdir(parents=True, exist_ok=True)

    records = extract_continual_learning_records(telemetry_db_path, conversations_db_path)

    # If CSV already exists and has manual edits, merge and preserve manual changes!
    existing_manual_edits: Dict[str, Dict[str, Any]] = {}
    if out_file.exists():
        try:
            with open(out_file, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rid = row.get("id")
                    if rid:
                        existing_manual_edits[rid] = row
        except Exception as exc:
            print(f"[DatasetExtractor] Note reading existing CSV: {exc}")

    fieldnames = [
        "id",
        "source_strategy",
        "raw_user_query",
        "training_input",
        "intent_label",
        "confidence",
        "human_verified",
        "human_action",
        "created_at",
    ]

    merged_records = []
    seen_ids = set()

    for r in records:
        rid = r["id"]
        seen_ids.add(rid)
        if rid in existing_manual_edits:
            # Preserve human edits from CSV if any
            m = existing_manual_edits[rid]
            r["intent_label"] = m.get("intent_label") or r["intent_label"]
            r["training_input"] = m.get("training_input") or r["training_input"]
            r["human_verified"] = m.get("human_verified") or r["human_verified"]
        merged_records.append(r)

    # Keep any additional manual rows added directly to CSV by user
    for rid, m in existing_manual_edits.items():
        if rid not in seen_ids:
            merged_records.append(m)

    with open(out_file, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged_records)

    print(f"[DatasetExtractor] Successfully exported {len(merged_records)} training records to {out_file}")
    return out_file


def append_single_interaction_to_csv(
    interaction_id: str,
    customer_query: str,
    predicted_intent: str,
    confidence: float,
    human_action: str = "AUTO_LLM",
    rewritten_query: Optional[str] = None,
    output_path: Optional[Path] = None,
) -> None:
    """Real-time instant sync: appends turn directly to CSV on every UI interaction."""
    out_file = output_path or DEFAULT_CSV_PATH
    out_file.parent.mkdir(parents=True, exist_ok=True)

    clean_q = " ".join((customer_query or "").split())
    if not clean_q or not predicted_intent:
        return

    words = clean_q.split()
    is_short = len(words) <= 4
    has_domain = any(
        k in clean_q.lower()
        for k in [
            "hủy", "huy", "cancel", "voucher", "mã giảm", "freeship", "giảm giá",
            "đổi trả", "hoàn tiền", "bảo hành", "nhân viên", "người thật"
        ]
    )

    if rewritten_query and rewritten_query.strip() and rewritten_query.strip() != clean_q:
        strategy = "3_rewritten"
        training_input = rewritten_query.strip()
    else:
        strategy = "1_standalone"
        training_input = clean_q

    fieldnames = [
        "id",
        "source_strategy",
        "raw_user_query",
        "training_input",
        "intent_label",
        "confidence",
        "human_verified",
        "human_action",
        "created_at",
    ]

    # Check if interaction already exists to avoid duplicates
    exists = False
    if out_file.exists():
        try:
            with open(out_file, "r", encoding="utf-8") as f:
                content = f.read()
                if interaction_id in content:
                    exists = True
        except Exception:
            pass

    if exists:
        return

    from datetime import datetime
    row = {
        "id": interaction_id,
        "source_strategy": strategy,
        "raw_user_query": clean_q,
        "training_input": training_input,
        "intent_label": predicted_intent,
        "confidence": round(confidence, 4),
        "human_verified": 1 if human_action in ("APPROVE", "EDIT") else 0,
        "human_action": human_action,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    file_is_new = not out_file.exists() or out_file.stat().st_size == 0
    with open(out_file, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if file_is_new:
            writer.writeheader()
        writer.writerow(row)


if __name__ == "__main__":
    export_dataset_to_csv()

