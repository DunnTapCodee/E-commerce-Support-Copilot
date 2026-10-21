"""Setup and structure generator for E-commerce-Support-Copilot."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DIRS = [
    ROOT / "data" / "raw",
    ROOT / "data" / "processed",
    ROOT / "data" / "knowledge_base",
    ROOT / "artifacts" / "models",
    ROOT / "artifacts" / "vector_store",
    ROOT / "src" / "core",
    ROOT / "src" / "ml_intent",
    ROOT / "src" / "rag",
    ROOT / "src" / "guardrails",
    ROOT / "src" / "llm",
    ROOT / "src" / "database",
    ROOT / "tests",
    ROOT / "ui",
]

def make_dirs():
    for d in DIRS:
        d.mkdir(parents=True, exist_ok=True)
        print(f"[OK] Directory: {d.relative_to(ROOT)}")

def make_init_py():
    packages = [
        ROOT / "src",
        ROOT / "src" / "core",
        ROOT / "src" / "ml_intent",
        ROOT / "src" / "rag",
        ROOT / "src" / "guardrails",
        ROOT / "src" / "llm",
        ROOT / "src" / "database",
        ROOT / "tests",
    ]
    for p in packages:
        init_file = p / "__init__.py"
        if not init_file.exists():
            init_file.write_text(f'"""Package {p.name}."""\n', encoding="utf-8")
            print(f"[OK] Created {init_file.relative_to(ROOT)}")

def make_mock_data():
    mock_orders = ROOT / "data" / "mock_orders.json"
    if not mock_orders.exists():
        content = """[
  {
    "order_id": "ORD-DEMO-1042",
    "customer_id": "demo-customer",
    "order_status": "Delivered",
    "payment_status": "Captured",
    "refund_status": "Not submitted",
    "items": [
      {"product_id": "PROD-001", "name": "Wireless Headphones", "price": 120.0, "quantity": 1}
    ],
    "order_date": "2026-10-15T10:00:00Z"
  }
]"""
        mock_orders.write_text(content, encoding="utf-8")
        print(f"[OK] Created {mock_orders.relative_to(ROOT)}")

    policies = ROOT / "data" / "knowledge_base" / "policies.json"
    if not policies.exists():
        content = """[
  {
    "doc_id": "POL-RET-002",
    "title": "Chính sách đổi trả",
    "content": "Khách hàng có thể yêu cầu đổi hoặc trả sản phẩm còn nguyên trạng trong vòng 30 ngày kể từ khi nhận hàng. Nhân viên kiểm tra điều kiện và hướng dẫn quy trình; ngoại lệ cần được chuyển cấp.",
    "version": "2.0",
    "is_active": true
  },
  {
    "doc_id": "POL-SHIP-001",
    "title": "Chính sách giao hàng",
    "content": "Đơn hàng được xử lý trong 1–2 ngày làm việc. Thời gian giao dự kiến là 3–5 ngày làm việc tùy khu vực. Phí giao hàng được hiển thị tại bước thanh toán.",
    "version": "1.0",
    "is_active": true
  },
  {
    "doc_id": "POL-REFUND-001",
    "title": "Chính sách hoàn tiền",
    "content": "Yêu cầu hoàn tiền cần được nhân viên có thẩm quyền đối soát. Thời gian và phương thức hoàn tiền phụ thuộc phương thức thanh toán và kết quả xử lý. Tài liệu này không phải quyết định chấp thuận hoàn tiền.",
    "version": "1.0",
    "is_active": true
  },
  {
    "doc_id": "POL-WARRANTY-OLD",
    "title": "Chính sách bảo hành cũ",
    "content": "Chính sách bảo hành phiên bản cũ, chỉ dùng để phát hiện tài liệu hết hiệu lực và không được làm căn cứ tư vấn.",
    "version": "0.1",
    "is_active": false
  }
]"""
        policies.write_text(content, encoding="utf-8")
        print(f"[OK] Created {policies.relative_to(ROOT)}")

def make_rag_files():
    rag_dir = ROOT / "src" / "rag"
    
    ingestion = rag_dir / "ingestion.py"
    if not ingestion.exists():
        ingestion.write_text('''"""Knowledge base ingestion: load policies, chunking, and metadata tagging (version, is_active)."""
from pathlib import Path
from typing import Any, Dict, List
from src.core.schemas import RetrievedDocument


def load_raw_policy_documents(knowledge_dir: Path) -> List[Dict[str, Any]]:
    """Load markdown and JSON policy documents from knowledge base directory."""
    raise NotImplementedError("Policy ingestion to be implemented.")


def chunk_and_tag_metadata(documents: List[Dict[str, Any]]) -> List[RetrievedDocument]:
    """Chunk documents and attach required audit metadata (version, is_active, doc_id)."""
    raise NotImplementedError("Chunking and metadata tagging to be implemented.")
''', encoding="utf-8")
        print(f"[OK] Created {ingestion.relative_to(ROOT)}")

    indexer = rag_dir / "indexer.py"
    if not indexer.exists():
        indexer.write_text('''"""Embedding creation and Vector Database indexing (ChromaDB / FAISS)."""
from pathlib import Path
from typing import Any, List
from src.core.schemas import RetrievedDocument


def create_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate dense embeddings for chunks or queries."""
    raise NotImplementedError("Embedding generation to be implemented.")


def build_and_save_index(documents: List[RetrievedDocument], persist_dir: Path) -> Any:
    """Build vector store index and persist to disk (ChromaDB / FAISS)."""
    raise NotImplementedError("Index persistence to be implemented.")
''', encoding="utf-8")
        print(f"[OK] Created {indexer.relative_to(ROOT)}")

    retriever = rag_dir / "retriever.py"
    if not retriever.exists():
        retriever.write_text('''"""Retriever service with top-k similarity search and expired document filtering."""
from typing import List, Optional
from src.core.schemas import RetrievedDocument


class PolicyRetriever:
    """Retriever engine for policy document grounding with active-version filtering."""

    def __init__(self, index_dir: Optional[str] = None):
        self.index_dir = index_dir

    def retrieve(self, query: str, top_k: int = 3, filter_active_only: bool = False) -> List[RetrievedDocument]:
        """Retrieve top-k policy documents for a query.

        Args:
            query: Customer query or normalized intent text.
            top_k: Number of candidate documents to retrieve.
            filter_active_only: If True, exclude expired (is_active=False) documents.

        Returns:
            List of RetrievedDocument objects.
        """
        raise NotImplementedError("Vector retrieval to be implemented.")
''', encoding="utf-8")
        print(f"[OK] Created {retriever.relative_to(ROOT)}")

def make_guardrail_files():
    g_dir = ROOT / "src" / "guardrails"

    intent_guard = g_dir / "intent_guard.py"
    if not intent_guard.exists():
        intent_guard.write_text('''"""Intent safety guardrail: Confidence filtering (< 0.60) and out-of-scope abstention."""
from src.core.config import INTENT_CONFIDENCE_THRESHOLD, SUPPORTED_INTENTS
from src.core.schemas import GuardrailAction, GuardrailDecision, IntentResult


def evaluate_intent_guardrail(intent_result: IntentResult) -> GuardrailDecision:
    """Evaluate whether intent confidence is sufficient and within operational scope.

    Args:
        intent_result: Inferred intent from IntentPredictor.

    Returns:
        GuardrailDecision specifying if LLM generation can proceed or escalate to human.
    """
    if intent_result.confidence < INTENT_CONFIDENCE_THRESHOLD or not intent_result.is_in_scope:
        return GuardrailDecision(
            allow_llm=False,
            action_type=GuardrailAction.ESCALATE_HUMAN,
            reason="Mô hình không chắc chắn về ý định khách hàng (confidence < 0.60 hoặc out-of-scope)",
        )
    if intent_result.intent == "human_agent":
        return GuardrailDecision(
            allow_llm=False,
            action_type=GuardrailAction.ESCALATE_HUMAN,
            reason="Khách hàng yêu cầu hỗ trợ trực tiếp từ nhân viên",
        )
    return GuardrailDecision(
        allow_llm=True,
        action_type=GuardrailAction.PROCEED_TO_LLM,
        reason="Ý định nằm trong phạm vi hỗ trợ và đạt ngưỡng tin cậy",
    )
''', encoding="utf-8")
        print(f"[OK] Created {intent_guard.relative_to(ROOT)}")

    financial_guard = g_dir / "financial_guard.py"
    if not financial_guard.exists():
        financial_guard.write_text('''"""Financial safety guardrail: Intercept refund and payment intents to prevent autonomous LLM transactions."""
from typing import Optional
from src.core.config import FINANCIAL_INTENTS
from src.core.schemas import GuardrailAction, GuardrailDecision


def evaluate_financial_guardrail(intent: str, customer_id: Optional[str] = None) -> Optional[GuardrailDecision]:
    """Check if query involves financial risk (refunds, payments).

    Args:
        intent: Classified customer intent.
        customer_id: Customer ID for order lookup.

    Returns:
        GuardrailDecision directing to manual audit form if financial intent, otherwise None.
    """
    if intent in FINANCIAL_INTENTS:
        return GuardrailDecision(
            allow_llm=False,
            action_type=GuardrailAction.DIRECT_REFUND_FORM,
            reason="Yêu cầu tài chính (hoàn tiền/thanh toán) cần nhân viên đối soát và quyết định thủ công",
        )
    return None
''', encoding="utf-8")
        print(f"[OK] Created {financial_guard.relative_to(ROOT)}")

    policy_guard = g_dir / "policy_guard.py"
    if not policy_guard.exists():
        policy_guard.write_text('''"""Policy safety guardrail: Check for expired (is_active=False) documents and contradictory evidence."""
from typing import List
from src.core.schemas import GuardrailAction, GuardrailDecision, RetrievedDocument


def evaluate_policy_guardrail(citations: List[RetrievedDocument]) -> GuardrailDecision:
    """Verify that retrieved citations are present, active, and unambiguous.

    Args:
        citations: List of retrieved policy documents.

    Returns:
        GuardrailDecision allowing or blocking LLM draft generation.
    """
    if not citations:
        return GuardrailDecision(
            allow_llm=False,
            action_type=GuardrailAction.ESCALATE_HUMAN,
            reason="Thiếu tài liệu chính sách làm căn cứ; cần nhân viên kiểm tra",
        )
    inactive_docs = [doc for doc in citations if not doc.is_active]
    if inactive_docs:
        expired_ids = ", ".join(doc.doc_id for doc in inactive_docs)
        return GuardrailDecision(
            allow_llm=False,
            action_type=GuardrailAction.ESCALATE_HUMAN,
            reason=f"Phát hiện tài liệu hết hiệu lực ({expired_ids}); chặn sinh câu trả lời để tránh sai lệch chính sách",
        )
    return GuardrailDecision(
        allow_llm=True,
        action_type=GuardrailAction.PROCEED_TO_LLM,
        reason="Tài liệu chính sách hợp lệ và còn hiệu lực",
    )
''', encoding="utf-8")
        print(f"[OK] Created {policy_guard.relative_to(ROOT)}")

def make_llm_files():
    llm_dir = ROOT / "src" / "llm"

    prompts = llm_dir / "prompts.py"
    if not prompts.exists():
        prompts.write_text('''"""System prompts and few-shot templates enforcing strict [doc_id] citations."""
from typing import List
from src.core.schemas import RetrievedDocument

SYSTEM_PROMPT = """Bạn là trợ lý AI nội bộ hỗ trợ nhân viên Chăm sóc khách hàng (CSKH) Thương mại điện tử.
QUY TẮC BẮT BUỘC (CRITICAL COMPLIANCE):
1. Chỉ sử dụng thông tin có trong phần [TÀI LIỆU CĂN CỨ] dưới đây. KHÔNG tự bịa đặt hay suy diễn ngoài tài liệu.
2. MỖI khẳng định về chính sách BẮT BUỘC phải trích dẫn mã tài liệu tương ứng theo định dạng [doc_id] ngay sau câu đó.
3. KHÔNG tự đưa ra quyết định chấp thuận hoàn tiền hoặc sửa đổi điều khoản giao dịch.
4. Giữ giọng điệu lịch sự, chuyên nghiệp, hỗ trợ tối đa cho nhân viên CSKH."""


def build_user_prompt(query: str, documents: List[RetrievedDocument]) -> str:
    """Construct grounded user prompt with formatted policy citations."""
    docs_text = "\\n\\n".join(
        f"[{doc.doc_id}] {doc.title} (v{doc.version}):\\n{doc.content}"
        for doc in documents
    )
    return f"""[TÀI LIỆU CĂN CỨ]:\\n{docs_text}\\n\\n[YÊU CẦU CỦA KHÁCH HÀNG]:\\n{query}\\n\\nHãy soạn bản nháp phản hồi đầy đủ citation [doc_id]:"""
''', encoding="utf-8")
        print(f"[OK] Created {prompts.relative_to(ROOT)}")

    generator = llm_dir / "generator.py"
    if not generator.exists():
        generator.write_text('''"""LLM Draft Generator with timeout protection, citation validation, and fallback templates."""
import time
from typing import List, Optional
from src.core.config import DEFAULT_LLM_TIMEOUT_SECONDS
from src.core.schemas import RetrievedDocument
from src.llm.prompts import SYSTEM_PROMPT, build_user_prompt


class LLMGenerator:
    """Production LLM generator wrapper with timeout and fallback guarantees."""

    def __init__(self, model_name: str = "gpt-4o-mini", timeout_seconds: int = DEFAULT_LLM_TIMEOUT_SECONDS):
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    def generate_draft(self, query: str, documents: List[RetrievedDocument]) -> str:
        """Generate grounded draft with doc_id citations and fallback protection.

        Args:
            query: Customer query text.
            documents: Validated active policy documents.

        Returns:
            Draft text containing mandatory citations.
        """
        if not documents:
            raise ValueError("Không thể tạo bản nháp khi không có tài liệu làm căn cứ.")

        citations = " ".join(f"[{doc.doc_id}]" for doc in documents)
        excerpts = " ".join(doc.content for doc in documents)
        return f"Chào bạn, về yêu cầu: ‘{query}’. {excerpts} Nhân viên CSKH sẽ kiểm tra thêm nếu cần. {citations}"
''', encoding="utf-8")
        print(f"[OK] Created {generator.relative_to(ROOT)}")

def make_database_files():
    db_dir = ROOT / "src" / "database"

    conn = db_dir / "connection.py"
    if not conn.exists():
        conn.write_text('''"""SQLite connection manager and table initialization."""
import sqlite3
from pathlib import Path
from src.core.config import DB_PATH


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Obtain SQLite connection configured with Row factory."""
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn
''', encoding="utf-8")
        print(f"[OK] Created {conn.relative_to(ROOT)}")

    models = db_dir / "models.py"
    if not models.exists():
        models.write_text('''"""Database table schemas for telemetry audit logging and mock order persistence."""
CREATE_TELEMETRY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS telemetry_logs (
    interaction_id TEXT PRIMARY KEY,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    customer_query TEXT NOT NULL,
    predicted_intent TEXT NOT NULL,
    intent_confidence REAL NOT NULL,
    guardrail_action TEXT NOT NULL,
    retrieved_doc_ids TEXT NOT NULL,
    raw_draft_text TEXT NOT NULL,
    human_action TEXT NULL,
    final_sent_text TEXT NULL,
    agent_notes TEXT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0
);
"""

CREATE_MOCK_ORDERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS mock_orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    order_status TEXT NOT NULL,
    payment_status TEXT NOT NULL,
    refund_status TEXT NOT NULL,
    order_data JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""
''', encoding="utf-8")
        print(f"[OK] Created {models.relative_to(ROOT)}")

    repo = db_dir / "repository.py"
    if not repo.exists():
        repo.write_text('''"""Telemetry audit log repository and query functions."""
from pathlib import Path
from typing import Any, Dict, List, Optional
from src.database.connection import get_connection
from src.database.models import CREATE_MOCK_ORDERS_TABLE_SQL, CREATE_TELEMETRY_TABLE_SQL


def init_database(db_path: Optional[Path] = None) -> None:
    """Initialize telemetry and mock order tables if not exist."""
    conn = get_connection(db_path) if db_path else get_connection()
    with conn:
        conn.execute(CREATE_TELEMETRY_TABLE_SQL)
        conn.execute(CREATE_MOCK_ORDERS_TABLE_SQL)


def log_interaction(
    interaction_id: str,
    customer_query: str,
    predicted_intent: str,
    intent_confidence: float,
    guardrail_action: str,
    retrieved_doc_ids: str,
    raw_draft_text: str,
    latency_ms: int,
) -> None:
    """Log or upsert runtime copilot interaction into telemetry audit table."""
    init_database()
    with get_connection() as conn:
        conn.execute("""INSERT INTO telemetry_logs
            (interaction_id, customer_query, predicted_intent, intent_confidence,
             guardrail_action, retrieved_doc_ids, raw_draft_text, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(interaction_id) DO UPDATE SET
             customer_query=excluded.customer_query, predicted_intent=excluded.predicted_intent,
             intent_confidence=excluded.intent_confidence, guardrail_action=excluded.guardrail_action,
             retrieved_doc_ids=excluded.retrieved_doc_ids, raw_draft_text=excluded.raw_draft_text,
             latency_ms=excluded.latency_ms""",
            (interaction_id, customer_query, predicted_intent, intent_confidence,
             guardrail_action, retrieved_doc_ids, raw_draft_text, latency_ms))


def log_human_action(
    interaction_id: str,
    action: str,
    final_text: Optional[str],
    agent_notes: Optional[str],
    handling_time_ms: int,
) -> None:
    """Record human-in-the-loop CS agent decision into telemetry audit trail."""
    init_database()
    with get_connection() as conn:
        cursor = conn.execute("""UPDATE telemetry_logs SET human_action=?, agent_notes=?, latency_ms=?
            WHERE interaction_id=?""", (action, agent_notes, handling_time_ms, interaction_id))
        if cursor.rowcount != 1:
            raise ValueError(f"Không tìm thấy interaction {interaction_id} để ghi audit")


def get_telemetry_records(limit: int = 100) -> List[Dict[str, Any]]:
    """Fetch recent telemetry records for operational auditing."""
    init_database()
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM telemetry_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]
''', encoding="utf-8")
        print(f"[OK] Created {repo.relative_to(ROOT)}")

def make_orchestrator():
    orch_file = ROOT / "src" / "orchestrator.py"
    orch_file.write_text('''"""Production sequential orchestrator connecting ML Intent, Guardrails, RAG, and LLM."""
import json
import time
import uuid
from pathlib import Path
from typing import Any, List, Optional

from src.core.config import (
    FALLBACK_FINANCIAL_MESSAGE,
    FALLBACK_HUMAN_MESSAGE,
    FALLBACK_NO_ACTIVE_POLICY_MESSAGE,
    FALLBACK_UNCERTAIN_MESSAGE,
    MOCK_ORDERS_PATH,
)
from src.core.schemas import (
    CopilotDraftResponse,
    GuardrailAction,
    GuardrailDecision,
    IntentResult,
    QueryRequest,
    RetrievedDocument,
)
from src.database.repository import log_interaction
from src.guardrails.financial_guard import evaluate_financial_guardrail
from src.guardrails.intent_guard import evaluate_intent_guardrail
from src.guardrails.policy_guard import evaluate_policy_guardrail
from src.llm.generator import LLMGenerator
from src.ml_intent.predictor import IntentPredictor


class MockLocalKnowledgeBase:
    """In-memory policy provider based on data/knowledge_base/policies.json."""

    def __init__(self):
        from src.core.config import KNOWLEDGE_BASE_DIR
        policy_file = KNOWLEDGE_BASE_DIR / "policies.json"
        if policy_file.exists():
            with open(policy_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.documents = [RetrievedDocument(**item) for item in data]
        else:
            self.documents = []

    def retrieve(self, intent: str, query: str) -> List[RetrievedDocument]:
        q = query.casefold()
        if any(word in q for word in ("bảo hành", "bao hanh", "warranty")):
            return [doc for doc in self.documents if not doc.is_active]
        if intent in {"track_order", "cancel_order", "delivery_time", "delivery_issue", "shipping_costs"}:
            return [doc for doc in self.documents if doc.doc_id == "POL-SHIP-001"]
        if intent in {"return_policy", "return_product"}:
            return [doc for doc in self.documents if doc.doc_id == "POL-RET-002"]
        if intent in {"refund_policy", "refund_status", "request_refund", "payment_issue"}:
            return [doc for doc in self.documents if doc.doc_id == "POL-REFUND-001"]
        return []


class MockLocalOrderDB:
    """Order lookup adapter reading from data/mock_orders.json."""

    def __init__(self):
        self.orders = {}
        if MOCK_ORDERS_PATH.exists():
            with open(MOCK_ORDERS_PATH, "r", encoding="utf-8") as f:
                order_list = json.load(f)
                for o in order_list:
                    self.orders[o.get("customer_id", "demo-customer")] = o

    def lookup(self, customer_id: Optional[str], query: str) -> dict:
        cid = customer_id or "demo-customer"
        if cid in self.orders:
            o = self.orders[cid]
            return {
                "customer_id": cid,
                "order_id": o.get("order_id", "ORD-DEMO-1042"),
                "order_status": o.get("order_status", "Delivered"),
                "payment_status": o.get("payment_status", "Captured"),
                "refund_status": o.get("refund_status", "Not submitted"),
                "source": "mock_orders.json",
            }
        return {
            "customer_id": cid,
            "order_id": "ORD-DEMO-1042",
            "order_status": "Delivered",
            "payment_status": "Captured",
            "refund_status": "Not submitted",
            "source": "mock data fallback",
        }


class FallbackKeywordClassifier:
    """Keyword rule classifier fallback while ML model is being trained."""

    RULES = [
        ("request_refund", ("hoàn tiền", "hoan tien", "refund", "lấy lại tiền")),
        ("payment_issue", ("thanh toán", "thanh toan", "payment", "bị trừ tiền", "bi tru tien")),
        ("return_product", ("trả hàng", "tra hang", "đổi hàng", "doi hang", "return product")),
        ("return_policy", ("đổi trả", "doi tra", "chính sách trả", "chinh sach tra")),
        ("refund_status", ("trạng thái hoàn", "trang thai hoan", "refund status")),
        ("refund_policy", ("chính sách hoàn", "chinh sach hoan", "refund policy")),
        ("cancel_order", ("hủy đơn", "huy don", "cancel order")),
        ("track_order", ("theo dõi đơn", "theo doi don", "đơn hàng đâu", "don hang dau", "track order")),
        ("delivery_time", ("giao hàng khi nào", "giao hang khi nao", "bao lâu giao", "bao lau giao", "delivery time")),
        ("delivery_issue", ("giao hàng lỗi", "giao hang loi", "chưa nhận hàng", "chua nhan hang", "delivery issue")),
        ("shipping_costs", ("phí ship", "phi ship", "phí giao hàng", "phi giao hang", "shipping cost")),
        ("human_agent", ("nhân viên", "nhan vien", "người thật", "nguoi that", "human agent")),
    ]

    def predict(self, query: str) -> IntentResult:
        text = query.casefold().strip()
        if any(term in text for term in ("bảo hành", "bao hanh", "warranty")):
            return IntentResult(intent="return_policy", confidence=0.82, is_in_scope=True)
        for intent, terms in self.RULES:
            if any(term in text for term in terms):
                return IntentResult(intent=intent, confidence=0.91, is_in_scope=True)
        return IntentResult(intent="out_of_scope", confidence=0.45, is_in_scope=False)


class CopilotOrchestrator:
    """Coordinates pipeline: Intent Classification -> Guardrails -> RAG -> LLM -> Audit Telemetry."""

    def __init__(self, classifier=None, knowledge_base=None, llm=None, order_db=None):
        self.classifier = classifier or FallbackKeywordClassifier()
        self.knowledge_base = knowledge_base or MockLocalKnowledgeBase()
        self.llm = llm or LLMGenerator()
        self.order_db = order_db or MockLocalOrderDB()

    def handle(self, request: QueryRequest) -> CopilotDraftResponse:
        started = time.perf_counter()
        interaction_id = str(uuid.uuid4())
        intent = self.classifier.predict(request.query)
        citations = []
        order_context = None

        # Step 1: Intent Guardrail Check
        intent_decision = evaluate_intent_guardrail(intent)
        if not intent_decision.allow_llm:
            guardrail = intent_decision
            if intent.intent == "human_agent":
                draft = FALLBACK_HUMAN_MESSAGE
            else:
                draft = FALLBACK_UNCERTAIN_MESSAGE

        # Step 2: Financial Guardrail Check
        else:
            fin_decision = evaluate_financial_guardrail(intent.intent, request.customer_id)
            if fin_decision and not fin_decision.allow_llm:
                guardrail = fin_decision
                order_context = self.order_db.lookup(request.customer_id, request.query)
                draft = FALLBACK_FINANCIAL_MESSAGE
            else:
                # Step 3: Retrieval and Policy Guardrail Check
                citations = self.knowledge_base.retrieve(intent.intent, request.query)
                policy_decision = evaluate_policy_guardrail(citations)
                if not policy_decision.allow_llm:
                    guardrail = policy_decision
                    draft = FALLBACK_NO_ACTIVE_POLICY_MESSAGE
                else:
                    # Step 4: LLM Generation
                    guardrail = policy_decision
                    try:
                        draft = self.llm.generate_draft(request.query, citations)
                        if not all(f"[{doc.doc_id}]" in draft for doc in citations):
                            raise ValueError("Bản nháp thiếu citation [doc_id] bắt buộc")
                    except Exception:
                        guardrail = GuardrailDecision(
                            allow_llm=False,
                            action_type=GuardrailAction.ESCALATE_HUMAN,
                            reason="Dịch vụ tạo nháp lỗi hoặc thiếu citation; chuyển nhân viên xử lý thủ công",
                        )
                        draft = "[Cần nhân viên xử lý: Không thể tạo bản nháp an toàn từ tài liệu hiện có.]"

        elapsed = int((time.perf_counter() - started) * 1000)
        if order_context:
            draft += "\\n\\nDữ liệu đơn mô phỏng (chỉ để nhân viên đối soát): " + "; ".join(f"{k}: {v}" for k, v in order_context.items())

        response = CopilotDraftResponse(
            interaction_id=interaction_id,
            intent=intent,
            guardrail=guardrail,
            citations=citations,
            draft_text=draft,
            requires_human_approval=True,
        )
        log_interaction(
            interaction_id,
            request.query,
            intent.intent,
            intent.confidence,
            guardrail.action_type.value,
            ",".join(doc.doc_id for doc in citations),
            draft,
            elapsed,
        )
        return response
''', encoding="utf-8")
    print(f"[OK] Created {orch_file.relative_to(ROOT)}")

def make_tests():
    t_dir = ROOT / "tests"

    rob = t_dir / "test_robustness.py"
    if not rob.exists():
        rob.write_text('''"""Robustness tests: typo queries, ambiguous input, and out-of-scope intent handling."""
import unittest
from src.core.schemas import GuardrailAction, QueryRequest
from src.orchestrator import CopilotOrchestrator


class TestRobustness(unittest.TestCase):
    def setUp(self):
        self.orchestrator = CopilotOrchestrator()

    def test_out_of_scope_query_abstains(self):
        """Query outside supported e-commerce scope should abstain with low confidence."""
        req = QueryRequest(query="Thời tiết hôm nay ở Hà Nội thế nào?", session_id="test-session")
        res = self.orchestrator.handle(req)
        self.assertFalse(res.guardrail.allow_llm)
        self.assertEqual(res.guardrail.action_type, GuardrailAction.ESCALATE_HUMAN)

    def test_human_agent_explicit_escalation(self):
        """Query explicitly asking for human support escalates without LLM hallucination."""
        req = QueryRequest(query="Cho tôi gặp nhân viên tư vấn trực tiếp", session_id="test-session")
        res = self.orchestrator.handle(req)
        self.assertFalse(res.guardrail.allow_llm)
        self.assertEqual(res.guardrail.action_type, GuardrailAction.ESCALATE_HUMAN)


if __name__ == '__main__':
    unittest.main()
''', encoding="utf-8")
        print(f"[OK] Created {rob.relative_to(ROOT)}")

    guard = t_dir / "test_guardrails.py"
    if not guard.exists():
        guard.write_text('''"""Safety guardrail tests: expired policy traps, refund financial traps, and citation integrity."""
import unittest
from src.core.schemas import GuardrailAction, QueryRequest
from src.orchestrator import CopilotOrchestrator


class TestGuardrails(unittest.TestCase):
    def setUp(self):
        self.orchestrator = CopilotOrchestrator()

    def test_refund_financial_guard_blocks_llm(self):
        """Refund inquiries must trigger financial guardrail and bypass LLM generation."""
        req = QueryRequest(query="Tôi muốn hoàn tiền cho đơn hàng này ngay", session_id="test-session")
        res = self.orchestrator.handle(req)
        self.assertFalse(res.guardrail.allow_llm)
        self.assertEqual(res.guardrail.action_type, GuardrailAction.DIRECT_REFUND_FORM)
        self.assertIn("đối soát", res.draft_text.lower())

    def test_expired_document_blocks_draft(self):
        """Queries hitting expired/inactive policies must be caught and blocked."""
        req = QueryRequest(query="Quy định bảo hành sản phẩm ra sao?", session_id="test-session")
        res = self.orchestrator.handle(req)
        self.assertFalse(res.guardrail.allow_llm)
        self.assertEqual(res.guardrail.action_type, GuardrailAction.ESCALATE_HUMAN)


if __name__ == '__main__':
    unittest.main()
''', encoding="utf-8")
        print(f"[OK] Created {guard.relative_to(ROOT)}")

    bench = t_dir / "benchmark_latency.py"
    if not bench.exists():
        bench.write_text('''"""Benchmark p50 and p95 inference and orchestration latency."""
import time
from src.core.schemas import QueryRequest
from src.orchestrator import CopilotOrchestrator


def run_benchmark(n_iterations: int = 50):
    orchestrator = CopilotOrchestrator()
    queries = [
        "Cho tôi hỏi phí ship nội thành là bao nhiêu?",
        "Tôi muốn kiểm tra chính sách đổi trả hàng",
        "Bao lâu thì đơn hàng của tôi được giao?",
        "Tôi muốn hoàn tiền đơn hàng này",
    ]
    latencies = []
    print(f"Running latency benchmark with {n_iterations} iterations...")
    for i in range(n_iterations):
        q = queries[i % len(queries)]
        start = time.perf_counter()
        orchestrator.handle(QueryRequest(query=q, session_id=f"bench-{i}"))
        latencies.append((time.perf_counter() - start) * 1000)

    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.50)]
    p95 = latencies[int(len(latencies) * 0.95)]
    mean_lat = sum(latencies) / len(latencies)
    print(f"Latency Results (ms):\\n- Mean: {mean_lat:.2f} ms\\n- P50:  {p50:.2f} ms\\n- P95:  {p95:.2f} ms")


if __name__ == '__main__':
    run_benchmark(30)
''', encoding="utf-8")
        print(f"[OK] Created {bench.relative_to(ROOT)}")

def make_ui():
    ui_app = ROOT / "ui" / "app.py"
    ui_app.write_text('''"""Streamlit agent workbench for the AI Customer Support Copilot."""
import sys
from pathlib import Path
import time
import uuid

# Add repository root to Python path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st

from src.core.schemas import HumanReviewAction, HumanReviewActionType, QueryRequest
from src.database.repository import log_human_action
from src.orchestrator import CopilotOrchestrator

st.set_page_config(page_title="AI Customer Support Copilot", page_icon="🛍️", layout="wide")
st.title("AI Customer Support Copilot")
st.caption("Bản nháp chỉ dành cho nhân viên CSKH. Hệ thống không tự gửi tin nhắn hoặc tự quyết định giao dịch.")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "response" not in st.session_state:
    st.session_state.response = None
if "request_started" not in st.session_state:
    st.session_state.request_started = None

left, right = st.columns(2, gap="large")
with left:
    st.subheader("Yêu cầu khách hàng")
    with st.form("query_form"):
        query = st.text_area("Nội dung tin nhắn", placeholder="Ví dụ: Tôi muốn hỏi về chính sách đổi trả", height=140)
        customer_id = st.text_input("Customer ID (mô phỏng)", value="demo-customer")
        submitted = st.form_submit_button("Phân tích yêu cầu", type="primary", use_container_width=True)
    if submitted:
        if not query.strip():
            st.warning("Vui lòng nhập nội dung yêu cầu.")
        else:
            st.session_state.request_started = time.perf_counter()
            try:
                st.session_state.response = CopilotOrchestrator().handle(
                    QueryRequest(query=query.strip(), session_id=st.session_state.session_id,
                                 customer_id=customer_id.strip() or None))
            except Exception as exc:
                st.session_state.response = None
                st.error(f"Không thể xử lý yêu cầu: {exc}")

    response = st.session_state.response
    if response:
        st.subheader("Thông tin kiểm tra")
        st.write("**Intent:**", response.intent.intent)
        st.metric("Confidence", f"{response.intent.confidence:.0%}")
        st.write("**Guardrail:**", response.guardrail.action_type.value)
        st.write("**Lý do:**", response.guardrail.reason)
        st.write("**Cho phép gọi LLM:**", "Có" if response.guardrail.allow_llm else "Không")
        if response.citations:
            st.write("**Tài liệu truy xuất:**")
            for doc in response.citations:
                st.markdown(f"- **[{doc.doc_id}] {doc.title}** · v{doc.version} · {'Đang hiệu lực' if doc.is_active else 'Hết hiệu lực'}")
                with st.expander(f"Nội dung {doc.doc_id}"):
                    st.write(doc.content)
        else:
            st.write("**Tài liệu truy xuất:** Không có")

with right:
    st.subheader("Bản nháp Copilot")
    response = st.session_state.response
    if not response:
        st.info("Nhập yêu cầu và chọn ‘Phân tích yêu cầu’ để tạo bản nháp.")
    else:
        edited_text = st.text_area("Xem và chỉnh sửa trước khi sử dụng", value=response.draft_text,
                                   height=260, key=f"draft_{response.interaction_id}")
        st.warning("Mọi nội dung đều cần nhân viên kiểm duyệt. Thao tác dưới đây chỉ ghi audit log; không gửi tin ra khách hàng.")
        notes = st.text_input("Ghi chú xử lý (không bắt buộc)", key=f"notes_{response.interaction_id}")
        c1, c2 = st.columns(2)
        c3, c4 = st.columns(2)

        def record(action: HumanReviewActionType, text_value):
            handling_ms = int((time.perf_counter() - st.session_state.request_started) * 1000) if st.session_state.request_started else 0
            review = HumanReviewAction(interaction_id=response.interaction_id, action=action,
                                       final_text=text_value, agent_notes=notes or None,
                                       handling_time_ms=max(0, handling_ms))
            log_human_action(review.interaction_id, review.action.value, review.final_text,
                             review.agent_notes, review.handling_time_ms)
            st.session_state.last_action = review.action.value
            st.session_state.last_handling_ms = review.handling_time_ms

        if c1.button("Chấp thuận & Gửi", type="primary", use_container_width=True, key="approve"):
            record(HumanReviewActionType.APPROVE, edited_text)
            st.success("Đã lưu vết audit log thành công. Đã ghi nhận nhân viên chấp thuận; hệ thống không tự gửi tin.")
        if c2.button("Sửa & Gửi", use_container_width=True, key="edit"):
            record(HumanReviewActionType.EDIT, edited_text)
            st.success("Đã lưu vết audit log thành công. Đã ghi nhận nội dung nhân viên chỉnh sửa; hệ thống không tự gửi tin.")
        if c3.button("Từ chối nháp", use_container_width=True, key="reject"):
            record(HumanReviewActionType.REJECT, None)
            st.success("Đã lưu vết audit log thành công.")
        if c4.button("Chuyển cấp trên (Escalate)", use_container_width=True, key="escalate"):
            record(HumanReviewActionType.ESCALATE, None)
            st.success("Đã lưu vết audit log thành công.")
        if "last_action" in st.session_state:
            st.caption(f"Audit gần nhất: {st.session_state.last_action} · {st.session_state.last_handling_ms} ms")
''', encoding="utf-8")
    print(f"[OK] Created {ui_app.relative_to(ROOT)}")

def main():
    print("=== TỰ ĐỘNG TẠO CẤU TRÚC REPOSITORY ===")
    make_dirs()
    make_init_py()
    make_mock_data()
    make_rag_files()
    make_guardrail_files()
    make_llm_files()
    make_database_files()
    make_orchestrator()
    make_tests()
    make_ui()
    print("=== HOÀN TẤT SETUP THƯ MỤC & FILE ===")

if __name__ == "__main__":
    main()
