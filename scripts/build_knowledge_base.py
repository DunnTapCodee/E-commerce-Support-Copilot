"""Build and validate Comprehensive Knowledge Base for E-commerce Customer Support Copilot.
Includes 26 curated Tiki/Shopee policies covering all 12 operational intents + expired policy traps.
"""
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from contracts.schemas import RetrievedDocument
from services.rag_service.src.indexer import PolicyVectorIndexer

POLICIES = [
    # 1. Đổi trả & Trả hàng
    {
        "doc_id": "POL-RET-001",
        "category": "return_refund",
        "title": "Chính sách và điều kiện đổi trả sản phẩm",
        "content": "Khách hàng có thể yêu cầu đổi hoặc trả sản phẩm trong vòng 30 ngày (đối với hàng Tiki Trading/Shopee Mall) hoặc 7 ngày (đối với gian hàng tiêu chuẩn) kể từ ngày nhận hàng thành công. Sản phẩm đổi trả phải còn nguyên tem mác, đầy đủ hộp, phụ kiện và quà tặng kèm, chưa có dấu hiệu đã qua sử dụng. Các mặt hàng hạn chế đổi trả bao gồm đồ lót, đồ bơi, mỹ phẩm đã bóc seal, hoặc sản phẩm có dấu hiệu hư hỏng do người dùng.",
        "version": "2.0",
        "is_active": True,
        "tags": ["đổi trả", "điều kiện đổi hàng", "trả hàng", "thời hạn đổi trả", "nguyên seal"]
    },
    {
        "doc_id": "POL-RET-002",
        "category": "return_refund",
        "title": "Quy trình và các bước tạo yêu cầu đổi trả trên ứng dụng",
        "content": "Để tạo yêu cầu đổi trả, khách hàng vào mục Tài khoản > Đơn hàng của tôi > Đã giao > Chọn đơn hàng cần đổi trả > Bấm 'Yêu cầu Đổi - Trả'. Khách hàng chụp hình ảnh hoặc quay video chứng minh lỗi sản phẩm (bể vỡ, sai mẫu, lỗi kỹ thuật). Sau khi yêu cầu được duyệt, nhân viên vận chuyển sẽ đến tận nhà thu hồi sản phẩm miễn phí trong vòng 1-2 ngày làm việc hoặc khách hàng có thể mang hàng ra điểm bưu cục gần nhất.",
        "version": "2.0",
        "is_active": True,
        "tags": ["quy trình đổi trả", "hướng dẫn trả hàng", "gửi hàng trả", "thu hồi hàng tận nhà"]
    },
    {
        "doc_id": "POL-RET-003",
        "category": "return_refund",
        "title": "Danh mục sản phẩm hạn chế đổi trả hoặc không áp dụng đổi ý",
        "content": "Các danh mục sản phẩm không được áp dụng chính sách đổi trả vì lý do không ưng ý/đổi ý gồm có: Thực phẩm tươi sống, thực phẩm bảo vệ sức khỏe, đồ lót, đồ ngủ, đồ bơi, mỹ phẩm/dược phẩm đã bóc màng bọc bảo vệ (seal), thẻ cào điện thoại, voucher dịch vụ điện tử, và các sản phẩm thanh lý xả kho có gắn nhãn không đổi trả. Các sản phẩm này chỉ được xem xét nếu giao sai mã hoặc lỗi kỹ thuật từ nhà sản xuất.",
        "version": "2.0",
        "is_active": True,
        "tags": ["danh mục hạn chế", "không được đổi trả", "đổi ý", "hàng tươi sống", "mỹ phẩm đã bóc"]
    },
    {
        "doc_id": "POL-RET-004",
        "category": "return_refund",
        "title": "Quy định đổi hàng do chọn nhầm kích cỡ hoặc màu sắc",
        "content": "Đối với sản phẩm thời trang, giày dép, nếu khách hàng mặc không vừa hoặc muốn đổi màu sắc, hệ thống hỗ trợ đổi hàng trong vòng 7 ngày kể từ khi nhận hàng. Khách hàng liên hệ với người bán qua tính năng Chat để thỏa thuận đổi kích cỡ. Trường hợp đổi size do nhu cầu cá nhân mà sản phẩm không có lỗi từ shop, khách hàng có thể phải thanh toán phí vận chuyển 2 chiều theo biểu phí của đơn vị vận chuyển.",
        "version": "1.5",
        "is_active": True,
        "tags": ["đổi size", "đổi màu sắc", "không vừa size", "chọn nhầm size", "đổi áo quần"]
    },

    # 2. Hoàn tiền
    {
        "doc_id": "POL-REFUND-001",
        "category": "return_refund",
        "title": "Quy định và nguyên tắc đối soát hoàn tiền",
        "content": "Yêu cầu hoàn tiền chỉ được xử lý khi đơn hàng đã hủy thành công trước khi xuất kho hoặc sau khi kho vận nhận và nghiệm thu sản phẩm trả về đạt tiêu chuẩn. Mọi quyết định hoàn tiền đều phải qua bước đối soát của nhân viên CSKH có thẩm quyền, AI không được phép tự động phê duyệt giao dịch tiền tệ. Phí giao hàng ban đầu sẽ không được hoàn trả nếu lý do đổi trả xuất phát từ nhu cầu cá nhân của khách hàng.",
        "version": "1.0",
        "is_active": True,
        "tags": ["nguyên tắc hoàn tiền", "đối soát", "hoàn tiền thủ công", "quy định hoàn tiền"]
    },
    {
        "doc_id": "POL-REFUND-002",
        "category": "return_refund",
        "title": "Thời gian và phương thức nhận tiền hoàn",
        "content": "Thời gian nhận lại tiền hoàn phụ thuộc vào phương thức thanh toán ban đầu: Đối với Ví điện tử (MoMo, ZaloPay, ShopeePay, VNPay), tiền hoàn về ví trong 24 giờ làm việc. Đối với Thẻ ATM nội địa (Napas) hoặc chuyển khoản, thời gian từ 3 đến 5 ngày làm việc. Đối với Thẻ tín dụng/ghi nợ quốc tế (Visa, Mastercard, JCB), ngân hàng phát hành xử lý trong 7 đến 15 ngày làm việc. Thời gian trên không tính Thứ Bảy, Chủ Nhật và ngày Lễ Tết.",
        "version": "2.0",
        "is_active": True,
        "tags": ["thời gian hoàn tiền", "bao lâu nhận lại tiền", "hoàn tiền ví momo", "hoàn tiền visa", "tiến độ hoàn tiền"]
    },
    {
        "doc_id": "POL-REFUND-003",
        "category": "return_refund",
        "title": "Chính sách hoàn trả mã giảm giá (Voucher) và tiền cước vận chuyển",
        "content": "Khi đơn hàng bị hủy hoặc được chấp thuận trả hàng hoàn tiền 100%, mã giảm giá của sàn (Sàn Voucher) sẽ tự động hoàn trả lại ví voucher của khách hàng trong vòng 1-3 giờ nếu voucher đó vẫn còn hạn sử dụng. Mã giảm giá từ phía Người bán (Shop Voucher) và mã Miễn phí vận chuyển đã dùng sẽ không được hoàn lại. Tiền phí ship đã thanh toán chỉ được hoàn nếu lỗi thuộc về người bán hoặc đơn vị vận chuyển.",
        "version": "1.0",
        "is_active": True,
        "tags": ["hoàn voucher", "mã giảm giá bị hủy", "hoàn phí ship", "voucher hoàn lại", "tiền ship hoàn"]
    },
    {
        "doc_id": "POL-REFUND-004",
        "category": "return_refund",
        "title": "Xử lý sự cố sai thông tin tài khoản nhận tiền hoàn hoặc tài khoản ngân hàng bị khóa",
        "content": "Nếu số tài khoản ngân hàng hoặc số điện thoại ví điện tử của khách hàng bị khóa, đổi số hoặc điền sai khi yêu cầu hoàn tiền, hệ thống sẽ gửi thông báo giao dịch thất bại. Khách hàng cần liên hệ trực tiếp với nhân viên CSKH và cung cấp ảnh chụp giấy tờ xác minh danh tính (CCCD/Hộ chiếu) cùng xác nhận số tài khoản mới để kế toán cập nhật lại lệnh chuyển tiền thủ công trong vòng 48 giờ.",
        "version": "1.0",
        "is_active": True,
        "tags": ["sai số tài khoản", "tài khoản bị khóa", "đổi tài khoản hoàn tiền", "lỗi chuyển khoản hoàn"]
    },

    # 3. Vận chuyển & Giao hàng
    {
        "doc_id": "POL-SHIP-001",
        "category": "shipping_delivery",
        "title": "Thời gian giao hàng dự kiến và các gói vận chuyển",
        "content": "Thời gian giao hàng dự kiến được chia theo gói dịch vụ: Gói Hỏa tốc (TikiNOW / Shopee Hỏa Tốc) nhận hàng trong vòng 2 giờ tại nội thành Hà Nội và TP.HCM. Gói Giao nhanh nhận hàng trong 1-2 ngày làm việc tại các thành phố lớn. Gói Giao tiêu chuẩn mất từ 3-5 ngày làm việc đối với đơn hàng liên tỉnh hoặc vùng xa. Trong các dịp khuyến mãi lớn hoặc thời tiết xấu, thời gian có thể kéo dài thêm 1-2 ngày.",
        "version": "1.0",
        "is_active": True,
        "tags": ["thời gian giao hàng", "mấy ngày nhận được hàng", "giao hàng hỏa tốc", "giao nhanh", "tiến độ giao"]
    },
    {
        "doc_id": "POL-SHIP-002",
        "category": "shipping_delivery",
        "title": "Biểu phí vận chuyển và chính sách hỗ trợ phí ship (Freeship)",
        "content": "Cước phí vận chuyển được tính tự động dựa trên khoảng cách và khối lượng kiện hàng: Đơn nội thành cước cơ bản từ 18.000đ đến 25.000đ. Đơn liên tỉnh cước từ 35.000đ đến 55.000đ. Đơn hàng đạt giá trị tối thiểu (từ 149.000đ hoặc 299.000đ tùy chương trình) được áp dụng mã giảm giá vận chuyển Freeship hỗ trợ tối đa 30.000đ - 70.000đ. Phí giao hàng cuối cùng hiển thị rõ tại trang thanh toán trước khi đặt đơn.",
        "version": "1.0",
        "is_active": True,
        "tags": ["phí vận chuyển", "phí ship", "tiền ship", "freeship", "miễn phí vận chuyển"]
    },
    {
        "doc_id": "POL-SHIP-003",
        "category": "shipping_delivery",
        "title": "Chính sách đồng kiểm hàng hóa khi nhận hàng",
        "content": "Khách hàng được quyền yêu cầu nhân viên giao hàng đồng kiểm trước khi ký nhận hoặc thanh toán COD. Phạm vi đồng kiểm bao gồm: mở hộp bọc ngoài để kiểm tra số lượng, tên sản phẩm, kích cỡ và ngoại quan bên ngoài xem có móp méo, trầy xước, vỡ hỏng hay không. Đồng kiểm không bao gồm việc xé tem niêm phong sản phẩm của nhà sản xuất hoặc cắm điện dùng thử máy móc. Nếu phát hiện sai sót, khách hàng có quyền từ chối nhận hàng và lập biên bản đồng kiểm.",
        "version": "2.0",
        "is_active": True,
        "tags": ["đồng kiểm", "kiểm tra hàng", "xem hàng trước khi thanh toán", "mở hàng", "quy định nhận hàng"]
    },
    {
        "doc_id": "POL-SHIP-004",
        "category": "shipping_delivery",
        "title": "Xử lý sự cố giao hàng trễ, thất lạc hoặc sai trạng thái",
        "content": "Trường hợp đơn hàng quá ngày dự kiến giao nhưng chưa nhận được, hoặc shipper đánh dấu 'Giao hàng thành công' nhưng khách hàng thực tế chưa nhận được kiện hàng, khách hàng cần liên hệ CSKH trong vòng 24-48 giờ. Đội ngũ điều phối sẽ kiểm tra định vị GPS của shipper, liên hệ bưu cục phát và xử lý khiếu nại. Nếu đơn hàng bị thất lạc, hệ thống sẽ gửi đơn thay thế hoặc hoàn trả 100% tiền đơn hàng cho khách.",
        "version": "1.0",
        "is_active": True,
        "tags": ["giao hàng trễ", "chưa nhận được hàng", "shipper không gọi", "sự cố giao nhận", "đơn hàng bị giao sai"]
    },
    {
        "doc_id": "POL-SHIP-005",
        "category": "shipping_delivery",
        "title": "Quy định giao hàng nhiều lần và thời gian lưu kho tại bưu cục",
        "content": "Nhân viên giao hàng sẽ liên hệ tối đa 3 lần vào các ngày khác nhau để giao kiện hàng. Nếu trong 3 lần phát hàng khách hàng đều bận hoặc không nghe máy, kiện hàng sẽ được lưu tại bưu cục phát gần nhất trong vòng 5 ngày. Khách hàng có thể chủ động liên hệ hotline bưu tá để hẹn lại thời gian giao hoặc trực tiếp đến bưu cục xuất trình mã vận đơn để nhận hàng trước khi kiện hàng bị chuyển hoàn về người bán.",
        "version": "1.0",
        "is_active": True,
        "tags": ["giao hàng 3 lần", "lưu kho bưu cục", "hẹn ngày giao", "chuyển hoàn hàng", "nhỡ cuộc gọi shipper"]
    },
    {
        "doc_id": "POL-SHIP-006",
        "category": "shipping_delivery",
        "title": "Vận chuyển hàng cồng kềnh, hàng siêu trường và đồ dễ vỡ",
        "content": "Đối với các sản phẩm kích thước lớn (như tủ lạnh, máy giặt, đệm, tivi trên 55 inch), kiện hàng được vận chuyển bằng đội xe chuyên dụng. Thời gian giao hàng có thể mất từ 3-7 ngày làm việc tùy địa bàn. Đơn vị vận chuyển hỗ trợ bưng bê lên tầng trệt; trường hợp cần hỗ trợ bê vác lên tầng lầu không có thang máy, khách hàng có thể thỏa thuận trực tiếp phụ phí nâng hạ với nhân viên giao nhận.",
        "version": "1.0",
        "is_active": True,
        "tags": ["hàng cồng kềnh", "tủ lạnh máy giặt", "bê lên lầu", "phụ phí vận chuyển", "hàng nặng"]
    },

    # 4. Đơn hàng & Quản lý
    {
        "doc_id": "POL-ORD-001",
        "category": "orders",
        "title": "Hướng dẫn tra cứu hành trình và trạng thái đơn hàng",
        "content": "Khách hàng có thể tra cứu tình trạng đơn hàng bằng cách vào mục 'Đơn hàng của tôi' trên ứng dụng. Các trạng thái đơn hàng bao gồm: 'Chờ xác nhận' (người bán chuẩn bị), 'Chờ lấy hàng' (đã đóng gói, chờ bưu tá), 'Đang giao hàng' (bưu tá đang vận chuyển, có mã vận đơn theo dõi trực tiếp), 'Đã giao' (hoàn tất) và 'Đã hủy'. Khách hàng có thể nhấn vào mã vận đơn để xem chi tiết từng trạm bưu cục kiện hàng đã đi qua.",
        "version": "1.0",
        "is_active": True,
        "tags": ["tra cứu đơn hàng", "tình trạng đơn hàng", "đơn hàng ở đâu", "mã vận đơn", "trạng thái đơn"]
    },
    {
        "doc_id": "POL-ORD-002",
        "category": "orders",
        "title": "Quy định và điều kiện hủy đơn hàng",
        "content": "Khách hàng có thể tự bấm nút 'Hủy đơn hàng' trực tiếp trên ứng dụng nếu đơn hàng đang ở trạng thái 'Chờ thanh toán' hoặc 'Chờ lấy hàng' mà chưa bàn giao cho đơn vị vận chuyển. Nếu đơn hàng đã được bàn giao cho bên vận chuyển (đang giao), hệ thống không hỗ trợ hủy trực tiếp; khách hàng vui lòng từ chối nhận hàng khi nhân viên giao hàng liên hệ. Đối với đơn hàng đã thanh toán trước bị hủy, tiền sẽ được hoàn trả tự động theo quy định hoàn tiền.",
        "version": "1.0",
        "is_active": True,
        "tags": ["hủy đơn hàng", "làm sao để hủy đơn", "hủy lệnh mua", "muốn hủy", "từ chối nhận hàng"]
    },
    {
        "doc_id": "POL-ORD-003",
        "category": "orders",
        "title": "Hướng dẫn thay đổi địa chỉ hoặc số điện thoại nhận hàng sau khi đặt",
        "content": "Khách hàng chỉ có thể thay đổi địa chỉ nhận hàng hoặc số điện thoại 01 lần duy nhất cho một đơn hàng nếu đơn hàng đó vẫn đang ở trạng thái 'Chờ xác nhận'. Khi đơn hàng đã chuyển sang trạng thái 'Đang chuẩn bị hàng' hoặc 'Đã giao cho đơn vị vận chuyển', hệ thống khóa tính năng sửa đổi để tránh thất lạc bưu kiện. Khách hàng vui lòng liên hệ bưu tá khi bưu tá gọi điện để thỏa thuận nhận hàng ở địa điểm lân cận.",
        "version": "1.0",
        "is_active": True,
        "tags": ["đổi địa chỉ", "đổi số điện thoại", "sửa địa chỉ nhận hàng", "giao sai địa chỉ"]
    },
    {
        "doc_id": "POL-ORD-004",
        "category": "orders",
        "title": "Quy định về xuất hóa đơn giá trị gia tăng (VAT) điện tử",
        "content": "Để yêu cầu xuất hóa đơn VAT, khách hàng cần tích chọn 'Yêu cầu hóa đơn VAT' và điền đầy đủ Tên công ty, Mã số thuế, Địa chỉ công ty và Email nhận hóa đơn tại bước thanh toán. Thời hạn yêu cầu hóa đơn là trong vòng 7 ngày kể từ khi đơn hàng được giao thành công. Hóa đơn điện tử hợp lệ theo quy định của Tổng cục Thuế sẽ được gửi qua email của khách hàng trong vòng 3 đến 5 ngày làm việc.",
        "version": "1.0",
        "is_active": True,
        "tags": ["hóa đơn vat", "xuất hóa đơn đỏ", "mã số thuế", "hóa đơn công ty", "hóa đơn điện tử"]
    },

    # 5. Thanh toán
    {
        "doc_id": "POL-PAY-001",
        "category": "payment",
        "title": "Xử lý sự cố thanh toán và giao dịch ngân hàng",
        "content": "Trường hợp tài khoản ngân hàng hoặc ví điện tử của khách hàng đã bị trừ tiền nhưng đơn hàng vẫn ở trạng thái 'Chưa thanh toán' hoặc không hiển thị đơn, nguyên nhân thường do độ trễ truyền dữ liệu từ cổng thanh toán. Hệ thống ngân hàng sẽ tự động đối soát và cập nhật đơn trong vòng 15-30 phút. Nếu sau 1 giờ đơn vẫn chưa cập nhật, cổng thanh toán sẽ tự động hoàn tiền lại tài khoản nguồn của khách hàng trong vòng 24-72 giờ làm việc.",
        "version": "1.0",
        "is_active": True,
        "tags": ["sự cố thanh toán", "bị trừ tiền chưa có đơn", "lỗi thanh toán", "lỗi ví momo", "thanh toán thất bại"]
    },
    {
        "doc_id": "POL-PAY-002",
        "category": "payment",
        "title": "Hướng dẫn các phương thức thanh toán hỗ trợ trên hệ thống",
        "content": "Hệ thống hỗ trợ đa dạng phương thức thanh toán an toàn: Thanh toán tiền mặt khi nhận hàng (COD), Thanh toán qua Ví điện tử (MoMo, ZaloPay, ShopeePay, VNPay-QR), Thẻ ATM nội địa Napas của hơn 40 ngân hàng, Thẻ tín dụng/ghi nợ quốc tế (Visa, Mastercard, JCB), Apple Pay, và Dịch vụ Mua trước trả sau (SPayLater/Home PayLater). Đối với đơn hàng có giá trị trên 20 triệu đồng, bắt buộc thanh toán trực tuyến trả trước.",
        "version": "1.0",
        "is_active": True,
        "tags": ["phương thức thanh toán", "thanh toán cod", "quẹt thẻ", "trả sau", "vnpay qr"]
    },
    {
        "doc_id": "POL-PAY-003",
        "category": "payment",
        "title": "Cảnh báo an toàn và bảo mật tài khoản giao dịch",
        "content": "Để đảm bảo an toàn giao dịch, khách hàng tuyệt đối không cung cấp mã xác thực OTP, mật khẩu tài khoản ngân hàng hoặc mật khẩu ví điện tử cho bất kỳ ai, kể cả người tự xưng là nhân viên CSKH của sàn. Hệ thống không bao giờ yêu cầu khách hàng chuyển tiền vào tài khoản cá nhân để nhận thưởng hay giải quyết khiếu nại. Khi phát hiện giao dịch bất thường, vui lòng khóa thẻ ngân hàng và liên hệ CSKH ngay lập tức.",
        "version": "1.0",
        "is_active": True,
        "tags": ["bảo mật thanh toán", "mã otp", "lừa đảo", "an toàn giao dịch", "bảo vệ tài khoản"]
    },

    # 6. Chăm sóc khách hàng & Khiếu nại
    {
        "doc_id": "POL-CS-001",
        "category": "support",
        "title": "Kênh liên hệ và khung giờ hỗ trợ nhân viên CSKH trực tiếp",
        "content": "Khách hàng có thể yêu cầu gặp nhân viên tư vấn trực tiếp qua các kênh chính thức: Tổng đài chăm sóc khách hàng 1900 6035 (hoạt động từ 8h00 đến 21h00 tất cả các ngày trong tuần, cước phí 1.000đ/phút), hoặc gửi yêu cầu qua kênh Live Chat trực tuyến 24/7 trên ứng dụng, hoặc gửi thư điện tử về hộp thư hotro@tiki.vn. Đối với các vấn đề khẩn cấp về khiếu nại tài chính và gian lận, nhân viên CSKH sẽ ưu tiên xử lý trong vòng 2-4 giờ.",
        "version": "1.0",
        "is_active": True,
        "tags": ["gặp nhân viên", "tổng đài cskh", "số điện thoại hỗ trợ", "chat với nhân viên", "human agent"]
    },
    {
        "doc_id": "POL-CS-002",
        "category": "support",
        "title": "Quy trình giải quyết khiếu nại và tranh chấp giữa người mua với người bán",
        "content": "Khi xảy ra mâu thuẫn về chất lượng hàng hóa hoặc thái độ phục vụ mà hai bên không đạt được thỏa thuận, khách hàng có thể bấm nút 'Khiếu nại người bán' trong chi tiết đơn hàng. Sàn TMĐT sẽ giữ vai trò trọng tài trung gian độc lập, yêu cầu cả người mua và người bán cung cấp bằng chứng (video đóng hàng, video mở hàng, ảnh chụp lỗi). Quyết định xử lý cuối cùng sẽ được ban hành trong vòng 3 đến 5 ngày làm việc.",
        "version": "1.0",
        "is_active": True,
        "tags": ["khiếu nại người bán", "tranh chấp đơn hàng", "tố cáo shop", "trọng tài sàn", "bằng chứng mở hàng"]
    },

    # 7. Bảo hành & Bẫy kiểm thử Guardrail (Safety Traps)
    {
        "doc_id": "POL-WARRANTY-001",
        "category": "warranty",
        "title": "Chính sách bảo hành sản phẩm điện tử và gia dụng chính hãng",
        "content": "Sản phẩm điện tử, công nghệ và thiết bị gia dụng chính hãng được áp dụng chính sách bảo hành tiêu chuẩn từ 12 đến 24 tháng theo quy định của nhà sản xuất. Khách hàng có thể bảo hành trực tiếp tại các trung tâm bảo hành ủy quyền của hãng trên toàn quốc bằng hóa đơn điện tử hoặc tem bảo hành, hoặc liên hệ Tiki/Shopee để được hỗ trợ bưu tá thu hồi sản phẩm gửi về hãng bảo hành miễn phí nếu sản phẩm còn trong thời hạn bảo hành.",
        "version": "2.0",
        "is_active": True,
        "tags": ["bảo hành", "chính sách bảo hành", "bảo hành điện tử", "sửa chữa", "bảo hành chính hãng"]
    },
    {
        "doc_id": "POL-WARRANTY-OLD",
        "category": "warranty",
        "title": "Chính sách bảo hành cũ áp dụng trước năm 2024",
        "content": "Chính sách bảo hành phiên bản cũ áp dụng trước ngày 01/01/2024. Tài liệu này hiện đã hết hiệu lực pháp lý và không được sử dụng làm căn cứ tư vấn cho khách hàng. Mọi yêu cầu bảo hành mới bắt buộc áp dụng theo quy chế bảo hành phiên bản 2.0 (POL-WARRANTY-001).",
        "version": "0.1",
        "is_active": False,
        "tags": ["bảo hành cũ", "chính sách hết hạn", "tài liệu cũ", "hết hiệu lực"]
    },
    {
        "doc_id": "POL-PROMO-OLD",
        "category": "promotions",
        "title": "Chương trình khuyến mãi và hoàn xu Tết Quý Mão 2023",
        "content": "Chương trình khuyến mãi hoàn 50% xu cho đơn hàng thời trang dịp Tết 2023. Chương trình này đã kết thúc thời gian áp dụng vào ngày 31/01/2023. Văn bản này đã hết hiệu lực và không còn giá trị tra cứu ưu đãi cho khách hàng ở thời điểm hiện tại.",
        "version": "0.5",
        "is_active": False,
        "tags": ["khuyến mãi cũ", "hoàn xu tết 2023", "chương trình hết hạn", "ưu đãi cũ"]
    }
]


def build_and_save():
    policy_path = ROOT_DIR / "data" / "knowledge_base" / "policies.json"
    index_path = ROOT_DIR / "artifacts" / "vector_store" / "policy_index.pkl"

    policy_path.parent.mkdir(parents=True, exist_ok=True)
    with open(policy_path, "w", encoding="utf-8") as f:
        json.dump(POLICIES, f, ensure_ascii=False, indent=2)

    print(f"✓ Saved {len(POLICIES)} policy documents to {policy_path}")

    # Index using PolicyVectorIndexer
    docs = [
        RetrievedDocument(
            doc_id=p["doc_id"],
            title=p["title"],
            content=p["content"],
            version=p["version"],
            is_active=p["is_active"],
            score=1.0,
        )
        for p in POLICIES
    ]

    indexer = PolicyVectorIndexer()
    indexer.fit_and_save(docs, index_path)
    print(f"✓ Built and saved vector index to {index_path}")

    # Verify search
    sample_queries = [
        "Tôi muốn đổi size áo có được không?",
        "Bao lâu thì tôi nhận lại được tiền hoàn về thẻ Visa?",
        "Hàng cồng kềnh máy giặt có bê lên lầu không?",
        "Cho tôi gặp nhân viên hỗ trợ",
        "Bảo hành cũ trước 2024 như thế nào",
    ]
    print("\n--- Testing Vector Search on Sample Queries ---")
    for q in sample_queries:
        res = indexer.search(q, top_k=2)
        top_doc, top_score = res[0]
        print(f"Q: '{q}' -> Top Doc: [{top_doc.doc_id}] {top_doc.title} (score: {top_score:.4f}, active: {top_doc.is_active})")


if __name__ == "__main__":
    build_and_save()
