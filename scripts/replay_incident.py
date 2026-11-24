"""Read-only PII-safe Incident Replay Extractor & Offline Reproducer (Task 6).

Extracts failed/anomalous interactions from SQLite telemetry & conversation DBs,
redacts phone numbers/emails/IDs via redact_pii(), writes replay JSON fixtures
plus optional offline unittest skeletons, and replays fixtures without network calls.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from contracts.schemas import IntentPredictionResponse, RetrievedDocument
from contracts.safety import evaluate_runtime_safety_envelope, is_intent_in_scope
from scripts.export_continual_learning_dataset import get_db_path, redact_pii
from services.conversation_service.src.policies.response_dispatcher import ResponsePolicyDispatcher


def _open_readonly_sqlite(db_path: Path) -> sqlite3.Connection:
    """Open SQLite database in read-only URI mode so production/dev DBs are never mutated."""
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def extract_incident_fixture(
    interaction_id: Optional[str] = None,
    session_id: Optional[str] = None,
    telemetry_db_path: Optional[Path] = None,
    conversations_db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Extract a PII-redacted incident fixture from SQLite logs (strictly read-only)."""
    if not interaction_id and not session_id:
        raise ValueError("Cần cung cấp --interaction-id hoặc --session-id.")

    tel_db = Path(telemetry_db_path or get_db_path("copilot_telemetry.sqlite3"))
    conv_db = Path(conversations_db_path or get_db_path("copilot_conversations.sqlite3"))

    telemetry_record: Optional[Dict[str, Any]] = None
    if interaction_id and tel_db.exists():
        with _open_readonly_sqlite(tel_db) as conn:
            row = conn.execute(
                """
                SELECT interaction_id, timestamp, customer_query, predicted_intent,
                       intent_confidence, guardrail_action, retrieved_doc_ids,
                       raw_draft_text, human_action, final_sent_text, agent_notes
                FROM telemetry_logs
                WHERE interaction_id = ?;
                """,
                (interaction_id,),
            ).fetchone()
            if row:
                telemetry_record = dict(row)

    session_meta: Optional[Dict[str, Any]] = None
    session_turns: List[Dict[str, Any]] = []
    if session_id and conv_db.exists():
        with _open_readonly_sqlite(conv_db) as conn:
            srow = conn.execute(
                "SELECT session_id, customer_id, active_intent, active_order_id, is_live_chat, copilot_draft FROM conversation_sessions WHERE session_id = ?;",
                (session_id,),
            ).fetchone()
            if srow:
                session_meta = dict(srow)
            trows = conn.execute(
                "SELECT turn_id, role, content, is_acknowledgement, intent, confidence FROM conversation_turns WHERE session_id = ? ORDER BY id ASC;",
                (session_id,),
            ).fetchall()
            session_turns = [
                {
                    "turn_id": t["turn_id"],
                    "role": t["role"],
                    "content": redact_pii(t["content"] or ""),
                    "is_acknowledgement": bool(t["is_acknowledgement"]),
                    "intent": t["intent"],
                    "confidence": t["confidence"],
                }
                for t in trows
            ]

    if not telemetry_record and not session_meta:
        raise LookupError("Không tìm thấy dữ liệu interaction_id hoặc session_id trong SQLite.")

    raw_query = (
        (telemetry_record.get("customer_query") if telemetry_record else None)
        or next((t["content"] for t in reversed(session_turns) if t["role"] == "customer"), "")
    )
    doc_ids = [
        d.strip()
        for d in str((telemetry_record or {}).get("retrieved_doc_ids") or "").split(",")
        if d.strip()
    ]

    return {
        "fixture_version": "1.0",
        "interaction_id": interaction_id or f"replay_{session_id}",
        "session_id": session_id,
        "pii_redacted": True,
        "customer_query": redact_pii(raw_query),
        "predicted_intent": (telemetry_record or {}).get("predicted_intent") or (session_meta or {}).get("active_intent") or "unknown_query",
        "intent_confidence": float((telemetry_record or {}).get("intent_confidence") or 0.0),
        "expected_guardrail_action": (telemetry_record or {}).get("guardrail_action"),
        "retrieved_doc_ids": doc_ids,
        "raw_draft_text": redact_pii((telemetry_record or {}).get("raw_draft_text") or (session_meta or {}).get("copilot_draft") or ""),
        "final_sent_text": redact_pii((telemetry_record or {}).get("final_sent_text") or ""),
        "agent_notes": redact_pii((telemetry_record or {}).get("agent_notes") or ""),
        "active_order_id": (session_meta or {}).get("active_order_id"),
        "is_live_chat": bool((session_meta or {}).get("is_live_chat", False)),
        "session_turns": session_turns,
    }


def replay_fixture_offline(fixture: Dict[str, Any]) -> Dict[str, Any]:
    """Re-evaluate a captured incident fixture strictly offline (DISABLES external LLM)."""
    os.environ["DISABLE_EXTERNAL_LLM"] = "true"
    intent_name = fixture.get("predicted_intent") or "unknown_query"
    conf = float(fixture.get("intent_confidence") or 0.0)
    intent_resp = IntentPredictionResponse(
        intent=intent_name,
        confidence=conf,
        is_in_scope=is_intent_in_scope(intent_name),
        all_probabilities={intent_name: conf},
    )
    citations = [
        RetrievedDocument(doc_id=did, title=did, content=f"Policy document {did}", is_active=True)
        for did in fixture.get("retrieved_doc_ids", [])
    ]
    guard, draft, suggested, guidance, mode = ResponsePolicyDispatcher.dispatch(
        user_query=fixture.get("customer_query") or "",
        input_type="new_question",
        intent_resp=intent_resp,
        order_data={"order_id": fixture["active_order_id"]} if fixture.get("active_order_id") else None,
        citations=citations,
        has_expired_policy=False,
        is_live_chat=bool(fixture.get("is_live_chat", False)),
    )
    runtime_env = evaluate_runtime_safety_envelope(
        customer_query=fixture.get("customer_query") or "",
        draft_text=fixture.get("raw_draft_text") or draft,
        order_data={"order_id": fixture["active_order_id"]} if fixture.get("active_order_id") else None,
        citations=citations if citations else None,
    )
    return {
        "interaction_id": fixture.get("interaction_id"),
        "dispatcher_mode": mode,
        "dispatcher_action": guard.action_type,
        "runtime_allow_llm": runtime_env.allow_llm,
        "runtime_action": runtime_env.action_type,
        "runtime_violations": runtime_env.violations,
        "guidance": guidance,
    }


def render_unittest_skeleton(fixture_path: Path, fixture: Dict[str, Any]) -> str:
    """Generate an offline unittest regression skeleton referencing the exported JSON fixture."""
    safe_id = "".join(ch if ch.isalnum() else "_" for ch in str(fixture.get("interaction_id", "case")))
    return f'''"""Auto-generated offline regression replay test for {fixture.get("interaction_id")}."""
import json
from pathlib import Path
import unittest

from scripts.replay_incident import replay_fixture_offline


class TestReplay_{safe_id}(unittest.TestCase):
    def test_replay_offline(self):
        fixture = json.loads(Path(r"{fixture_path}").read_text(encoding="utf-8"))
        result = replay_fixture_offline(fixture)
        self.assertTrue(fixture.get("pii_redacted"))
        self.assertIn("dispatcher_action", result)


if __name__ == "__main__":
    unittest.main()
'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract PII-safe incident replay fixture and run offline replay.")
    parser.add_argument("--interaction-id", default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--tel-db", type=Path, default=None)
    parser.add_argument("--conv-db", type=Path, default=None)
    parser.add_argument("--out-json", type=Path, default=None)
    parser.add_argument("--out-test", type=Path, default=None)
    args = parser.parse_args()

    fixture = extract_incident_fixture(
        interaction_id=args.interaction_id,
        session_id=args.session_id,
        telemetry_db_path=args.tel_db,
        conversations_db_path=args.conv_db,
    )
    replay_result = replay_fixture_offline(fixture)

    out_json = args.out_json or (ROOT_DIR / "reports" / "replays" / f"{fixture['interaction_id']}.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.out_test:
        args.out_test.parent.mkdir(parents=True, exist_ok=True)
        args.out_test.write_text(render_unittest_skeleton(out_json, fixture), encoding="utf-8")

    print(json.dumps({"fixture_path": str(out_json), "replay_result": replay_result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
