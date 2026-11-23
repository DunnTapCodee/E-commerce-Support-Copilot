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
    "unauthorized_order_access": (
        "Dạ Tiki chào anh/chị! Để đảm bảo bảo mật thông tin tài khoản và đơn hàng cá nhân, "
        "em chỉ có thể tra cứu các đơn hàng thuộc đúng tài khoản đang đăng nhập của anh/chị ạ. "
        "Anh/chị vui lòng cung cấp mã đơn hàng thuộc tài khoản của mình để em kiểm tra hỗ trợ ngay nhé!"
    ),
    "manipulation_voucher_escalate": (
        "Dạ Tiki chào anh/chị! Em đã ghi nhận phản ánh về ưu đãi/voucher và quyền lợi hỗ trợ trước đó của mình. "
        "Do các khoản cấp bù voucher hoặc bồi thường đều cần kiểm tra lịch sử xác thực trên hệ thống, "
        "em xin phép chuyển thông tin này tới chuyên viên CSKH cấp cao kiểm tra và phản hồi chính xác nhất cho anh/chị ạ."
    ),
    "warehouse_seal_blocked": (
        "Dạ Tiki chào anh/chị! Theo quy trình niêm phong và an toàn kho vận của Tiki, "
        "hệ thống không thể mở kiện hàng đã đóng gói hoặc chèn thêm giấy tờ bên ngoài vào kiện hàng. "
        "Em xin phép chuyển yêu cầu của anh/chị sang bộ phận CSKH chuyên trách để kiểm tra phương án hỗ trợ phù hợp ạ."
    ),
    "brand_comparison_neutral": (
        "Dạ Tiki chào anh/chị! Tiki luôn lắng nghe và trân trọng mọi góp ý của quý khách nhằm cải thiện chất lượng phục vụ [POL-BRAND-001]. "
        "Em xin phép giữ lập trường trung lập, không bình luận hay so sánh với các sàn thương mại điện tử khác; "
        "nếu anh/chị đang gặp vấn đề với đơn hàng hoặc chính sách tại Tiki, em rất sẵn sàng kiểm tra và hỗ trợ mình ngay ạ!"
    ),
}

AGENT_GUIDANCE = {
    "financial_risk": (
        "🔴 CẢNH BÁO TÀI CHÍNH: Phát hiện yêu cầu hoàn tiền / lỗi thanh toán. "
        "LLM bị khóa tuyệt đối để phòng ngừa rủi ro thất thoát. "
        "Vui lòng nhấn nút 'Xem hồ sơ đối soát' để kiểm tra dữ liệu đơn hàng và thực hiện quy trình kế toán."
    ),
    "unauthorized_order_access": (
        "🔴 CẢNH BÁO BẢO MẬT (IDOR): Khách hàng hỏi mã khách/mã đơn không thuộc tài khoản phiên hiện tại. "
        "Hệ thống đã chặn truy xuất đơn hàng chéo tài khoản và không hiển thị PII của khách hàng khác."
    ),
    "manipulation_risk": (
        "🔴 CẢNH BÁO THAO TÚNG VOUCHER / BỒI THƯỜNG: Khách hàng nhắc tới cam kết miệng/voucher chưa xác thực. "
        "LLM bị khóa để không tự ý hứa cấp voucher ngoài thẩm quyền. Nhân viên kiểm tra log cũ trước khi phản hồi."
    ),
    "warehouse_seal": (
        "🔴 CẢNH BÁO QUY TRÌNH KHO: Khách hàng yêu cầu mở kiện niêm phong hoặc chèn giấy tờ ngoài quy định. "
        "LLM bị khóa để không hứa thao tác kho trái quy trình."
    ),
    "brand_sensitivity": (
        "🟠 CẢNH BÁO NHẠY CẢM THƯƠNG HIỆU [POL-BRAND-001]: Tin nhắn có yếu tố công kích thương hiệu hoặc bẫy so sánh đối thủ. "
        "Hệ thống đã chuyển sang mẫu phản hồi trung lập. Nhân viên vui lòng kiểm tra kỹ trước khi bấm gửi."
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
