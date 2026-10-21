"""Canonical intent vocabulary and legacy smoke examples (never used by main training)."""
from typing import Dict, List, Tuple

TARGET_INTENTS: List[str] = [
    "track_order",
    "cancel_order",
    "delivery_time",
    "delivery_issue",
    "shipping_costs",
    "return_policy",
    "return_product",
    "refund_policy",
    "request_refund",
    "refund_status",
    "payment_issue",
    "human_agent",
]

OOS_LABEL = "out_of_scope"

# Canonical Bitext labels. Seed examples below are smoke data only.
ALL_BITEXT_INTENTS: List[str] = ['add_product', 'availability', 'availability_in_store', 'availability_online', 'cancel_order', 'change_account', 'change_order', 'close_account', 'customer_service', 'damaged_delivery', 'delivery_issue', 'delivery_time', 'exchange_product', 'exchange_product_in_store', 'human_agent', 'missing_item', 'open_account', 'order_history', 'pay', 'payment_issue', 'payment_methods', 'product_information', 'product_issue', 'recover_password', 'refund_policy', 'refund_status', 'remove_product', 'request_invoice', 'request_refund', 'request_right_to_rectification', 'return_policy', 'return_product', 'return_product_in_store', 'return_product_online', 'sales_period', 'shipping_costs', 'store_location', 'store_opening_hours', 'submit_feedback', 'submit_product_feedback', 'submit_product_idea', 'technical_issue', 'track_delivery', 'track_order', 'use_app', 'wrong_item']

# Legacy smoke examples only; train/validation/test are built by pipeline.data.
SEED_EXAMPLES: List[Tuple[str, str]] = [
    # track_order
    ("đơn hàng của tôi đang ở đâu", "track_order"),
    ("kiểm tra tình trạng đơn hàng ORD-1042", "track_order"),
    ("cho mình hỏi đơn hàng đã xuất kho chưa", "track_order"),
    ("where is my order right now", "track_order"),
    ("track my parcel ORD-8891", "track_order"),
    ("theo dõi tiến độ giao hàng", "track_order"),
    ("cho tôi xem định vị đơn hàng", "track_order"),
    
    # cancel_order
    ("tôi muốn hủy đơn hàng vừa đặt", "cancel_order"),
    ("làm cách nào để hủy đơn", "cancel_order"),
    ("hủy giúp tôi đơn ORD-9901 vì tôi đặt nhầm", "cancel_order"),
    ("cancel my order please", "cancel_order"),
    ("i want to cancel purchase", "cancel_order"),
    ("hủy lệnh mua hàng gấp", "cancel_order"),
    ("dừng giao hàng và hủy đơn cho tôi", "cancel_order"),

    # delivery_time
    ("bao giờ tôi nhận được hàng", "delivery_time"),
    ("thời gian giao hàng mất bao lâu", "delivery_time"),
    ("dự kiến mấy ngày nữa có hàng vậy shop", "delivery_time"),
    ("when will my order arrive", "delivery_time"),
    ("how long does shipping take", "delivery_time"),
    ("giao hàng tiêu chuẩn mất bao nhiêu ngày", "delivery_time"),
    ("khi nào shipper giao đến nơi", "delivery_time"),

    # delivery_issue
    ("shipper chưa giao mà hệ thống báo đã giao", "delivery_issue"),
    ("đơn hàng bị giao trễ quá lâu", "delivery_issue"),
    ("chưa nhận được hàng mặc dù quá hạn 5 ngày", "delivery_issue"),
    ("delivery delay issue, parcel not received", "delivery_issue"),
    ("courier marked delivered but i received nothing", "delivery_issue"),
    ("gặp sự cố khi nhận hàng shipper không liên lạc được", "delivery_issue"),

    # shipping_costs
    ("phí vận chuyển là bao nhiêu", "shipping_costs"),
    ("tiền ship tính thế nào shop ơi", "shipping_costs"),
    ("có được miễn phí giao hàng không", "shipping_costs"),
    ("what is the shipping fee", "shipping_costs"),
    ("how much does delivery cost", "shipping_costs"),
    ("phí ship giao hàng hỏa tốc là bao nhiêu", "shipping_costs"),

    # return_policy
    ("chính sách đổi trả hàng như thế nào", "return_policy"),
    ("thời hạn đổi hàng là bao nhiêu ngày", "return_policy"),
    ("điều kiện để trả lại sản phẩm", "return_policy"),
    ("what is the return policy", "return_policy"),
    ("how many days do i have to return an item", "return_policy"),
    ("quy định trả hàng có yêu cầu nguyên tem mác không", "return_policy"),

    # return_product
    ("tôi muốn gửi trả lại sản phẩm này", "return_product"),
    ("hướng dẫn tôi cách đóng gói gửi trả hàng", "return_product"),
    ("sản phẩm không vừa kích cỡ tôi muốn trả lại", "return_product"),
    ("i want to return this product", "return_product"),
    ("step to return items back to warehouse", "return_product"),
    ("cho tôi xin địa chỉ để gửi trả hàng lại", "return_product"),

    # refund_policy
    ("chính sách hoàn tiền của shop ra sao", "refund_policy"),
    ("tiền sẽ được hoàn qua tài khoản ngân hàng hay ví", "refund_policy"),
    ("quy định về việc hoàn tiền đơn hàng bị hủy", "refund_policy"),
    ("what is the refund policy", "refund_policy"),
    ("how do you process refund money", "refund_policy"),
    ("hoàn tiền mất bao nhiêu ngày làm việc", "refund_policy"),

    # request_refund
    ("tôi muốn yêu cầu hoàn lại tiền đơn này", "request_refund"),
    ("hãy hoàn tiền vào tài khoản ngân hàng cho tôi", "request_refund"),
    ("tôi muốn lấy lại tiền vì sản phẩm không đúng mô tả", "request_refund"),
    ("i demand a refund immediately", "request_refund"),
    ("please refund my money to credit card", "request_refund"),
    ("hoàn lại tiền ngay lập tức cho tôi", "request_refund"),

    # refund_status
    ("tiền hoàn của tôi đã về chưa", "refund_status"),
    ("kiểm tra trạng thái hoàn tiền đơn ORD-1042", "refund_status"),
    ("shop đã gửi lệnh hoàn tiền sang ngân hàng chưa", "refund_status"),
    ("what is the status of my refund", "refund_status"),
    ("check refund status for my transaction", "refund_status"),
    ("bao giờ tài khoản tôi mới nhận được tiền hoàn", "refund_status"),

    # payment_issue
    ("tài khoản bị trừ tiền 2 lần nhưng đơn chưa xác nhận", "payment_issue"),
    ("lỗi thanh toán thẻ tín dụng không thành công", "payment_issue"),
    ("tôi thanh toán qua ví bị trừ tiền mà đơn báo thất bại", "payment_issue"),
    ("payment failed but card was charged", "payment_issue"),
    ("double charged for one single order", "payment_issue"),
    ("gặp lỗi khi quét mã QR thanh toán", "payment_issue"),

    # human_agent
    ("cho tôi gặp nhân viên tư vấn trực tiếp", "human_agent"),
    ("tôi muốn nói chuyện với nhân viên chăm sóc khách hàng", "human_agent"),
    ("gặp người thật hỗ trợ chứ không nói với bot", "human_agent"),
    ("connect me to a human support agent", "human_agent"),
    ("i want to talk to customer service representative", "human_agent"),
    ("chuyển máy cho tổng đài viên", "human_agent"),
]

# Thêm các câu mẫu cho các intent out-of-scope/other để model học phân biệt 46 classes
OUT_OF_SCOPE_SAMPLES: List[Tuple[str, str]] = [
    ("tôi muốn đổi mật khẩu tài khoản", "recover_password"),
    ("quên mật khẩu đăng nhập", "recover_password"),
    ("tạo tài khoản mới thế nào", "create_account"),
    ("đăng ký thành viên mới", "create_account"),
    ("chính sách bảo hành sản phẩm điện tử", "warranty"),
    ("bảo hành máy hút bụi bao lâu", "warranty"),
    ("cho tôi xin mã giảm giá khuyến mãi", "get_discounts"),
    ("voucher giảm 50k áp dụng thế nào", "get_discounts"),
    ("thời tiết hôm nay thế nào", "out_of_scope"),
    ("bạn có biết nấu phở bò không", "out_of_scope"),
    ("thủ đô của nước Pháp là gì", "out_of_scope"),
]


def generate_bitext_dataframe():
    """Legacy smoke helper; not an evaluation or training corpus."""
    import pandas as pd
    data = []
    # Expand seed data with variations
    for query, intent in SEED_EXAMPLES:
        data.append({"query": query, "intent": intent})
        data.append({"query": query.lower(), "intent": intent})
        data.append({"query": query.upper(), "intent": intent})
        data.append({"query": f"Làm ơn {query}", "intent": intent})
        data.append({"query": f"Please help: {query}", "intent": intent})

    for query, intent in OUT_OF_SCOPE_SAMPLES:
        data.append({"query": query, "intent": intent})
        data.append({"query": f"Cho mình hỏi {query}", "intent": intent})

    df = pd.DataFrame(data)
    return df


def get_train_test_splits(test_size: float = 0.2, random_state: int = 42):
    """Legacy smoke split retained for external callers; not used by Module 1."""
    from sklearn.model_selection import train_test_split
    df = generate_bitext_dataframe()
    X = df["query"]
    y = df["intent"]
    return train_test_split(X, y, test_size=test_size, random_state=random_state, stratify=y)
