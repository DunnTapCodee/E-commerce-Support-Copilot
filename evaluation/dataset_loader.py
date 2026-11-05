"""Evaluation Dataset Loader for CMU MLIP Testing Suite.
Provides sliced test cases, perturbations, and metadata for behavioral and statistical tests.
"""
from typing import Any, Dict, List
from pydantic import BaseModel


class EvaluationTestCase(BaseModel):
    id: str
    query: str
    ground_truth_intent: str
    slice_type: str  # clean, typo_unaccented, polite, short, long_complex, adversarial, out_of_scope
    expected_entities: Dict[str, str] = {}
    expected_guardrail_action: str = "PROCEED_TO_LLM"
    description: str = ""


# Comprehensive benchmark dataset (~120 diverse test cases across all e-commerce domains)
BENCHMARK_DATASET: List[EvaluationTestCase] = [
    # -------------------------------------------------------------
    # 1. track_order (Tra cứu đơn hàng)
    # -------------------------------------------------------------
    EvaluationTestCase(
        id="TO-01",
        query="Kiểm tra đơn hàng ORD-1100 giúp mình với",
        ground_truth_intent="track_order",
        slice_type="clean",
        expected_entities={"order_id": "ORD-1100"},
        description="Standard order tracking with order ID",
    ),
    EvaluationTestCase(
        id="TO-02",
        query="kiem tra don hang ord-1002 giup minh",
        ground_truth_intent="track_order",
        slice_type="typo_unaccented",
        expected_entities={"order_id": "ORD-1002"},
        description="Unaccented lowercase order tracking",
    ),
    EvaluationTestCase(
        id="TO-03",
        query="Dạ em chào shop ạ, shop kiểm tra giúp em xem kiện hàng ORD-1001 hiện đang nằm ở bưu cục nào rồi ạ em cảm ơn shop",
        ground_truth_intent="track_order",
        slice_type="polite",
        expected_entities={"order_id": "ORD-1001"},
        description="Polite verbose inquiry with greeting and gratitude",
    ),
    EvaluationTestCase(
        id="TO-04",
        query="đơn của tôi đâu",
        ground_truth_intent="track_order",
        slice_type="short",
        description="Terse 4-word query without order ID",
    ),
    EvaluationTestCase(
        id="TO-05",
        query="Tôi đặt mua chuột máy tính từ tuần trước mà sao tra trên app thấy đứng yên ở kho trung tâm mấy ngày nay không thấy di chuyển tiếp, mã đơn là ORD-1100, số điện thoại tôi là 0998708581",
        ground_truth_intent="track_order",
        slice_type="long_complex",
        expected_entities={"order_id": "ORD-1100", "phone": "0998708581"},
        description="Long narrative query with background story",
    ),

    # -------------------------------------------------------------
    # 2. cancel_order (Hủy đơn hàng)
    # -------------------------------------------------------------
    EvaluationTestCase(
        id="CO-01",
        query="Tôi muốn hủy đơn hàng ORD-1002",
        ground_truth_intent="cancel_order",
        slice_type="clean",
        expected_entities={"order_id": "ORD-1002"},
        description="Standard order cancellation request",
    ),
    EvaluationTestCase(
        id="CO-02",
        query="huy don ord-1003 giup minh gap nhe",
        ground_truth_intent="cancel_order",
        slice_type="typo_unaccented",
        expected_entities={"order_id": "ORD-1003"},
        description="Unaccented urgent cancellation",
    ),
    EvaluationTestCase(
        id="CO-03",
        query="hủy đơn",
        ground_truth_intent="cancel_order",
        slice_type="short",
        description="Minimalist 2-word cancellation",
    ),
    EvaluationTestCase(
        id="CO-04",
        query="Do tôi đặt nhầm kích cỡ sản phẩm và địa chỉ nhận hàng nên shop vui lòng cho tôi hủy đơn ORD-1004 này nhé tôi sẽ đặt lại cái khác",
        ground_truth_intent="cancel_order",
        slice_type="long_complex",
        expected_entities={"order_id": "ORD-1004"},
        description="Detailed cancellation reasoning",
    ),

    # -------------------------------------------------------------
    # 3. delivery_time (Thời gian giao hàng)
    # -------------------------------------------------------------
    EvaluationTestCase(
        id="DT-01",
        query="Khoảng mấy ngày nữa thì hàng mới tới nơi?",
        ground_truth_intent="delivery_time",
        slice_type="clean",
        description="Standard delivery timeframe inquiry",
    ),
    EvaluationTestCase(
        id="DT-02",
        query="bao gio giao toi ha shop",
        ground_truth_intent="delivery_time",
        slice_type="typo_unaccented",
        description="Unaccented delivery time query",
    ),
    EvaluationTestCase(
        id="DT-03",
        query="thời gian giao",
        ground_truth_intent="delivery_time",
        slice_type="short",
        description="Short 3-word query",
    ),
    EvaluationTestCase(
        id="DT-04",
        query="Mình ở khu vực quận Cầu Giấy Hà Nội thì thời gian giao hàng tiêu chuẩn mất bao lâu vậy bạn?",
        ground_truth_intent="delivery_time",
        slice_type="polite",
        description="Location-specific delivery timeframe question",
    ),

    # -------------------------------------------------------------
    # 4. delivery_issue (Sự cố giao hàng)
    # -------------------------------------------------------------
    EvaluationTestCase(
        id="DI-01",
        query="Shipper không gọi điện mà hệ thống lại báo giao hàng không thành công",
        ground_truth_intent="delivery_issue",
        slice_type="clean",
        description="Shipper delivery failure complaint",
    ),
    EvaluationTestCase(
        id="DI-02",
        query="shipper giao tre qua 5 ngay roi van chua thay hang dau",
        ground_truth_intent="delivery_issue",
        slice_type="typo_unaccented",
        description="Severe delay delivery issue",
    ),
    EvaluationTestCase(
        id="DI-03",
        query="giao hàng trễ",
        ground_truth_intent="delivery_issue",
        slice_type="short",
        description="Short complaint",
    ),
    EvaluationTestCase(
        id="DI-04",
        query="Đơn ORD-1002 của tôi trên app hiển thị đã phát thành công lúc 8h sáng nhưng tôi và cả bảo vệ tòa nhà đều chưa hề nhận được gói hàng nào",
        ground_truth_intent="delivery_issue",
        slice_type="long_complex",
        expected_entities={"order_id": "ORD-1002"},
        description="False delivery success complaint",
    ),

    # -------------------------------------------------------------
    # 5. shipping_costs (Cước phí vận chuyển)
    # -------------------------------------------------------------
    EvaluationTestCase(
        id="SC-01",
        query="Phí ship giao về Đà Nẵng là bao nhiêu tiền?",
        ground_truth_intent="shipping_costs",
        slice_type="clean",
        description="Shipping fee calculation query",
    ),
    EvaluationTestCase(
        id="SC-02",
        query="phi ship bao nhieu",
        ground_truth_intent="shipping_costs",
        slice_type="typo_unaccented",
        description="Unaccented shipping cost query",
    ),
    EvaluationTestCase(
        id="SC-03",
        query="có được freeship không",
        ground_truth_intent="shipping_costs",
        slice_type="short",
        description="Free shipping eligibility question",
    ),

    # -------------------------------------------------------------
    # 6. return_policy (Chính sách đổi trả)
    # -------------------------------------------------------------
    EvaluationTestCase(
        id="RP-01",
        query="Quy định đổi trả hàng trong vòng bao nhiêu ngày?",
        ground_truth_intent="return_policy",
        slice_type="clean",
        description="General return policy inquiry",
    ),
    EvaluationTestCase(
        id="RP-02",
        query="chinh sach doi tra hang nhu the nao",
        ground_truth_intent="return_policy",
        slice_type="typo_unaccented",
        description="Unaccented policy inquiry",
    ),
    EvaluationTestCase(
        id="RP-03",
        query="Dạ shop cho em hỏi điều kiện để được đổi sản phẩm mới là gì ạ",
        ground_truth_intent="return_policy",
        slice_type="polite",
        description="Polite condition inquiry",
    ),

    # -------------------------------------------------------------
    # 7. return_product (Yêu cầu đổi trả sản phẩm cụ thể)
    # -------------------------------------------------------------
    EvaluationTestCase(
        id="RPR-01",
        query="Tôi nhận được áo bị rách đường chỉ ở nách, tôi muốn đổi cái khác",
        ground_truth_intent="return_product",
        slice_type="clean",
        description="Specific defective item exchange request",
    ),
    EvaluationTestCase(
        id="RPR-02",
        query="muon tra lai cai quan bi chat",
        ground_truth_intent="return_product",
        slice_type="typo_unaccented",
        description="Wrong size return request",
    ),
    EvaluationTestCase(
        id="RPR-03",
        query="đổi hàng bị lỗi",
        ground_truth_intent="return_product",
        slice_type="short",
        description="Short product return demand",
    ),

    # -------------------------------------------------------------
    # 8. refund_policy (Chính sách hoàn tiền)
    # -------------------------------------------------------------
    EvaluationTestCase(
        id="RFP-01",
        query="Chính sách hoàn tiền khi hủy đơn quy định thời hạn bao lâu?",
        ground_truth_intent="refund_policy",
        slice_type="clean",
        description="General refund policy question",
    ),
    EvaluationTestCase(
        id="RFP-02",
        query="quy dinh hoan tien cua shop the nao",
        ground_truth_intent="refund_policy",
        slice_type="typo_unaccented",
        description="Unaccented refund rules query",
    ),

    # -------------------------------------------------------------
    # 9. request_refund (Yêu cầu hoàn tiền - FINANCIAL RISK)
    # -------------------------------------------------------------
    EvaluationTestCase(
        id="RR-01",
        query="Hoàn tiền lại cho tôi ngay lập tức vào số tài khoản này",
        ground_truth_intent="request_refund",
        slice_type="clean",
        expected_guardrail_action="DIRECT_REFUND_FORM",
        description="Direct refund demand requiring financial guard",
    ),
    EvaluationTestCase(
        id="RR-02",
        query="tra lai tien cho toi vao vi momo",
        ground_truth_intent="request_refund",
        slice_type="typo_unaccented",
        expected_guardrail_action="DIRECT_REFUND_FORM",
        description="Direct refund unaccented demand",
    ),
    EvaluationTestCase(
        id="RR-03",
        query="hoàn tiền ngay",
        ground_truth_intent="request_refund",
        slice_type="short",
        expected_guardrail_action="DIRECT_REFUND_FORM",
        description="Urgent refund request",
    ),

    # -------------------------------------------------------------
    # 10. refund_status (Tra cứu tiến độ hoàn tiền)
    # -------------------------------------------------------------
    EvaluationTestCase(
        id="RS-01",
        query="Tiền hoàn của đơn hàng đã về tài khoản ngân hàng chưa shop?",
        ground_truth_intent="refund_status",
        slice_type="clean",
        description="Checking status of completed refund",
    ),
    EvaluationTestCase(
        id="RS-02",
        query="tien hoan da ve vi chua",
        ground_truth_intent="refund_status",
        slice_type="typo_unaccented",
        description="Unaccented refund status inquiry",
    ),

    # -------------------------------------------------------------
    # 11. payment_issue (Sự cố thanh toán - FINANCIAL RISK)
    # -------------------------------------------------------------
    EvaluationTestCase(
        id="PI-01",
        query="Tôi bị trừ tiền 2 lần qua thẻ tín dụng khi thanh toán đơn hàng",
        ground_truth_intent="payment_issue",
        slice_type="clean",
        expected_guardrail_action="DIRECT_REFUND_FORM",
        description="Double deduction payment problem",
    ),
    EvaluationTestCase(
        id="PI-02",
        query="loi thanh toan vnpay bi tru tien nhung khong co don",
        ground_truth_intent="payment_issue",
        slice_type="typo_unaccented",
        expected_guardrail_action="DIRECT_REFUND_FORM",
        description="Payment gateway deducted without order",
    ),

    # -------------------------------------------------------------
    # 12. human_agent (Gặp nhân viên hỗ trợ trực tiếp)
    # -------------------------------------------------------------
    EvaluationTestCase(
        id="HA-01",
        query="Cho tôi gặp nhân viên tư vấn người thật đi, bot nói chuyện chán quá",
        ground_truth_intent="human_agent",
        slice_type="clean",
        expected_guardrail_action="ESCALATE_HUMAN",
        description="Explicit request for human CS agent",
    ),
    EvaluationTestCase(
        id="HA-02",
        query="gap truc tiep nhan vien cskh",
        ground_truth_intent="human_agent",
        slice_type="typo_unaccented",
        expected_guardrail_action="ESCALATE_HUMAN",
        description="Unaccented staff handover",
    ),
    EvaluationTestCase(
        id="HA-03",
        query="gặp nhân viên",
        ground_truth_intent="human_agent",
        slice_type="short",
        expected_guardrail_action="ESCALATE_HUMAN",
        description="Short 2-word escalation",
    ),

    # -------------------------------------------------------------
    # 13. out_of_scope (Ngoại phạm vi e-commerce)
    # -------------------------------------------------------------
    EvaluationTestCase(
        id="OOS-01",
        query="Thời tiết Hà Nội ngày mai có mưa rào không bạn?",
        ground_truth_intent="out_of_scope",
        slice_type="out_of_scope",
        expected_guardrail_action="ESCALATE_HUMAN",
        description="Weather question outside domain",
    ),
    EvaluationTestCase(
        id="OOS-02",
        query="Giải phương trình bậc 2: 2x^2 + 5x - 3 = 0",
        ground_truth_intent="out_of_scope",
        slice_type="out_of_scope",
        expected_guardrail_action="ESCALATE_HUMAN",
        description="Math problem outside domain",
    ),
    EvaluationTestCase(
        id="OOS-03",
        query="Thủ đô của nước Pháp là thành phố nào vậy bot",
        ground_truth_intent="out_of_scope",
        slice_type="out_of_scope",
        expected_guardrail_action="ESCALATE_HUMAN",
        description="Geography trivia question",
    ),

    # -------------------------------------------------------------
    # 14. adversarial (Câu hỏi khó, đổi ý, bẫy dữ liệu)
    # -------------------------------------------------------------
    EvaluationTestCase(
        id="ADV-01",
        query="Ban đầu định hủy đơn nhưng thôi không hủy đơn nữa, cho mình hỏi bao giờ hàng tới nơi?",
        ground_truth_intent="delivery_time",
        slice_type="adversarial",
        description="Negation reversal from cancel_order to delivery_time",
    ),
    EvaluationTestCase(
        id="ADV-02",
        query="Hôm trước tôi có xem chính sách bảo hành cũ năm 2022 được đổi 3 ngày, giờ áp dụng chính sách nào?",
        ground_truth_intent="return_policy",
        slice_type="adversarial",
        description="Expired policy trap mentioning 2022 superseded policy",
    ),
    EvaluationTestCase(
        id="ADV-03",
        query="Tôi muốn trả hàng nhưng không phải do tôi không thích mà do hàng bị vỡ nát",
        ground_truth_intent="return_product",
        slice_type="adversarial",
        description="Nuanced distinction between return policy vs defective product",
    ),
]


def get_all_test_cases() -> List[EvaluationTestCase]:
    return BENCHMARK_DATASET


def get_cases_by_slice(slice_name: str) -> List[EvaluationTestCase]:
    return [c for c in BENCHMARK_DATASET if c.slice_type == slice_name]


def get_all_slice_types() -> List[str]:
    return sorted(list({c.slice_type for c in BENCHMARK_DATASET}))


def get_all_target_intents() -> List[str]:
    return sorted(list({c.ground_truth_intent for c in BENCHMARK_DATASET}))
