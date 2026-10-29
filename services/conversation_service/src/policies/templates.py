"""Structured macro response templates and agent guidance messages."""
from __future__ import annotations


MACRO_TEMPLATES = {
    "refund_pending": (
        "Dạ Tiki chào anh/chị, em đã tiếp nhận yêu cầu đối soát hoàn tiền cho đơn hàng {order_id}. "
        "Do liên quan trực tiếp đến giao dịch tài chính, em đang chuyển hồ sơ sang bộ phận Kế toán đối soát "
        "và sẽ phản hồi kết quả chi tiết đến anh/chị trong vòng 24h làm việc tới ạ."
    ),
    "refund_general": (
        "Dạ Tiki chào anh/chị, em đã tiếp nhận yêu cầu khiếu nại hoàn tiền / thanh toán của mình. "
        "Hồ sơ đang được chuyển sang bộ phận Kế toán để đối soát giao dịch và phản hồi đến anh/chị trong thời gian sớm nhất ạ."
    ),
    "expired_policy_buffer": (
        "Dạ em đã ghi nhận thắc mắc của anh/chị về chương trình này. Để hỗ trợ kiểm tra thông tin chính xác nhất "
        "theo từng thời điểm áp dụng, em đang kết nối mình với chuyên viên hỗ trợ. Anh/chị chờ em trong giây lát nhé ạ!"
    ),
    "chitchat_greeting": (
        "Dạ Tiki chào anh/chị! Rất vui được hỗ trợ mình hôm nay. Anh/chị cần em hỗ trợ thông tin gì về đơn hàng "
        "hoặc chính sách mua sắm không ạ?"
    ),
    "chitchat_thanks": (
        "Dạ không có gì ạ! Chúc anh/chị có trải nghiệm mua sắm thật vui vẻ cùng Tiki. "
        "Nếu cần hỗ trợ thêm bất cứ điều gì, anh/chị cứ nhắn cho em nhé!"
    ),
    "chitchat_confirm": (
        "Dạ em đã ghi nhận thông tin của anh/chị. Em đang kiểm tra giúp mình ngay đây ạ!"
    ),
    "live_chat_activated": (
        "Dạ em là chuyên viên hỗ trợ của Tiki đây ạ. Em đã tiếp nhận phiên hỗ trợ trực tiếp. "
        "Anh/chị chia sẻ giúp em chi tiết vấn đề mình đang cần hỗ trợ nhé!"
    ),
}

AGENT_GUIDANCE = {
    "financial_risk": (
        "🔴 CẢNH BÁO TÀI CHÍNH: Phát hiện yêu cầu hoàn tiền / lỗi thanh toán. "
        "LLM bị khóa tuyệt đối để phòng ngừa rủi ro thất thoát. "
        "Vui lòng nhấn nút 'Xem hồ sơ đối soát' để kiểm tra dữ liệu đơn hàng và thực hiện quy trình kế toán."
    ),
    "low_confidence": (
        "🟡 CẢNH BÁO NGỮ CẢNH: Câu hỏi có độ tin cậy thấp hoặc chưa rõ ý. "
        "Hệ thống không phỏng đoán bừa bãi mã đơn. "
        "Vui lòng đọc lại lịch sử chat bên dưới để nắm bắt nguyện vọng của khách và tự gõ câu trả lời."
    ),
    "live_chat": (
        "🔵 CHẾ ĐỘ CHAT TRỰC TIẾP: Khách hàng chủ động yêu cầu gặp nhân viên trực tiếp. "
        "Đã tắt toàn bộ gợi ý AI tự động, bạn đang trong phiên trao đổi trực tiếp với khách."
    ),
    "expired_policy": (
        "🟠 CẢNH BÁO PHÁP LÝ: Khách hàng hỏi về chính sách/ưu đãi cũ đã hết hiệu lực. "
        "Đã khóa LLM để tránh cam kết sai luật. Sử dụng câu đệm an toàn để chuyển giao."
    ),
    "happy_path": (
        "🟢 BẢN NHÁP COPILOT SẴN SÀNG: Câu hỏi hợp lệ, chính sách còn hạn và không phát hiện ảo giác. "
        "Vui lòng kiểm tra nhanh nội dung nháp bên dưới trước khi bấm duyệt gửi cho khách."
    ),
}
