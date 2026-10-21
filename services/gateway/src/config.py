"""Gateway configuration and downstream service endpoints."""
import os

INTENT_SERVICE_URL = os.getenv("INTENT_SERVICE_URL", "http://127.0.0.1:8005")
RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://127.0.0.1:8002")
TELEMETRY_SERVICE_URL = os.getenv("TELEMETRY_SERVICE_URL", "http://127.0.0.1:8003")

INTENT_CONFIDENCE_THRESHOLD = 0.60

FINANCIAL_INTENTS = {"request_refund", "payment_issue"}

FALLBACK_UNCERTAIN_MESSAGE = (
    "[Hệ thống tự động chuyển tiếp: Yêu cầu nằm ngoài phạm vi hoặc không rõ ý (confidence < 0.60)]"
)
FALLBACK_HUMAN_MESSAGE = (
    "[Hệ thống tự động chuyển tiếp: Khách hàng yêu cầu hỗ trợ trực tiếp từ nhân viên]"
)
FALLBACK_FINANCIAL_MESSAGE = (
    "Hệ thống phát hiện yêu cầu hoàn tiền/thanh toán. Vui lòng đối soát dữ liệu đơn bên dưới và ra quyết định thủ công."
)
FALLBACK_NO_ACTIVE_POLICY_MESSAGE = (
    "[Cần nhân viên xử lý: Không tìm thấy tài liệu phù hợp hoặc tài liệu đã hết hiệu lực. Không tự động khẳng định.]"
)
