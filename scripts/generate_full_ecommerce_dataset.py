"""Comprehensive Dataset Generator:
1. 50 Rich Policies & FAQs (data/knowledge_base/policies.json)
2. 100 Realistic E-commerce Mock Orders (data/mock_orders.json)
3. 100 Evaluation Benchmark Scenarios (data/benchmark_scenarios.json)
4. Rebuild Vector Index (artifacts/vector_store/policy_index.pkl)
"""
import json
import random
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

# ==============================================================================
# PART 1: 50 POLICIES & FAQS (STATIC KNOWLEDGE BASE)
# ==============================================================================
POLICIES = [
    # --- 1. Đổi trả hàng (8 policies) ---
    {
        "doc_id": "POL-RET-001",
        "category": "return_refund",
        "title": "Chính sách và điều kiện đổi trả sản phẩm tiêu chuẩn",
        "content": "Khách hàng có thể yêu cầu đổi hoặc trả sản phẩm trong vòng 30 ngày (đối với hàng Tiki Trading hoặc Shopee Mall) hoặc trong vòng 7 ngày (đối với gian hàng tiêu chuẩn) kể từ ngày nhận hàng thành công. Sản phẩm đổi trả phải còn nguyên tem mác, đầy đủ bao bì hộp, phụ kiện, hóa đơn và quà tặng kèm, chưa có dấu hiệu đã qua sử dụng hay giặt tẩy.",
        "version": "2.0",
        "is_active": True,
        "tags": ["đổi trả", "điều kiện đổi trả", "thời hạn đổi trả", "30 ngày", "7 ngày", "nguyên tem"]
    },
    {
        "doc_id": "POL-RET-002",
        "category": "return_refund",
        "title": "Quy trình và các bước tạo yêu cầu đổi trả trên ứng dụng",
        "content": "Để tạo yêu cầu đổi trả, khách hàng vào mục 'Tài khoản' > 'Đơn hàng của tôi' > Chọn đơn hàng đã giao > Bấm 'Yêu cầu Đổi - Trả'. Khách hàng chụp 3-5 ảnh rõ nét hoặc quay video thể hiện lỗi sản phẩm. Sau khi yêu cầu được phê duyệt, bưu tá sẽ đến tận nhà thu hồi miễn phí trong 1-2 ngày làm việc hoặc khách hàng có thể gửi tại bưu cục gần nhất.",
        "version": "2.0",
        "is_active": True,
        "tags": ["quy trình đổi trả", "hướng dẫn trả hàng", "các bước đổi hàng", "thu hồi tại nhà"]
    },
    {
        "doc_id": "POL-RET-003",
        "category": "return_refund",
        "title": "Danh mục sản phẩm hạn chế đổi trả hoặc không áp dụng đổi ý",
        "content": "Các danh mục sản phẩm không hỗ trợ trả hàng do đổi ý hoặc nhu cầu cá nhân gồm: Đồ lót, đồ bơi, mỹ phẩm và hóa chất đã bóc màng bọc bảo vệ (seal), thực phẩm tươi sống, thực phẩm chức năng, thẻ nạp điện thoại, voucher điện tử, và hàng thanh lý có ghi chú không đổi trả. Các mặt hàng này chỉ được đổi trả khi giao sai mẫu hoặc có lỗi kỹ thuật từ nhà sản xuất.",
        "version": "2.0",
        "is_active": True,
        "tags": ["danh mục hạn chế", "không được đổi trả", "đổi ý", "đồ lót", "mỹ phẩm bóc seal", "thực phẩm tươi"]
    },
    {
        "doc_id": "POL-RET-004",
        "category": "return_refund",
        "title": "Quy định đổi hàng do chọn nhầm kích cỡ hoặc màu sắc",
        "content": "Đối với sản phẩm thời trang, giày dép, khách hàng được hỗ trợ đổi kích cỡ (size) hoặc màu sắc trong vòng 7 ngày kể từ khi nhận hàng. Khách hàng liên hệ với người bán qua tính năng Chat để chọn kích cỡ thay thế. Trường hợp đổi hàng do nhu cầu chủ quan của khách hàng, khách hàng thanh toán chi phí vận chuyển phát sinh 2 chiều theo cước bưu điện.",
        "version": "1.5",
        "is_active": True,
        "tags": ["đổi size", "đổi kích cỡ", "đổi màu", "không vừa áo", "không vừa giày"]
    },
    {
        "doc_id": "POL-RET-005",
        "category": "return_refund",
        "title": "Quy định đổi trả hàng bị hư hỏng hoặc bể vỡ do vận chuyển",
        "content": "Trường hợp sản phẩm bị móp méo, trầy xước, nứt vỡ hoặc biến dạng do quá trình vận chuyển, khách hàng cần thông báo cho bộ phận CSKH trong vòng 48 giờ kể từ lúc nhận hàng. Khách hàng vui lòng giữ nguyên thùng hàng và cung cấp biên bản đồng kiểm hoặc video mở hàng để được ưu tiên gửi sản phẩm mới thay thế trong 24 giờ mà không phát sinh thêm chi phí.",
        "version": "2.0",
        "is_active": True,
        "tags": ["hàng bể vỡ", "hàng móp méo", "lỗi vận chuyển", "hư hỏng do bưu tá", "video mở hàng"]
    },
    {
        "doc_id": "POL-RET-006",
        "category": "return_refund",
        "title": "Chính sách đổi trả đối với hàng công nghệ và thiết bị điện tử",
        "content": "Sản phẩm điện thoại, máy tính bảng, laptop và máy ảnh được hỗ trợ 1 đổi 1 trong 30 ngày đầu nếu phát sinh lỗi phần cứng do nhà sản xuất (được xác nhận bởi trung tâm bảo hành hãng). Khách hàng cần gửi máy về kho kiểm định kèm theo đầy đủ phụ kiện, dây sạc, sách hướng dẫn và hộp trùng số IMEI/Serial.",
        "version": "2.0",
        "is_active": True,
        "tags": ["đổi trả đồ điện tử", "lỗi phần cứng", "đổi điện thoại", "1 đổi 1 trong 30 ngày"]
    },
    {
        "doc_id": "POL-RET-007",
        "category": "return_refund",
        "title": "Thời gian kiểm định và phản hồi yêu cầu trả hàng tại kho",
        "content": "Khi kiện hàng hoàn trả được bưu tá chuyển về kho bãi của sàn TMĐT, đội ngũ kỹ thuật sẽ tiến hành kiểm tra ngoại quan và chức năng trong vòng 2-3 ngày làm việc. Kết quả nghiệm thu (Chấp thuận hoàn tiền hoặc Từ chối do vi phạm điều kiện) sẽ được gửi thông báo tự động qua ứng dụng và email đã đăng ký của khách hàng.",
        "version": "1.0",
        "is_active": True,
        "tags": ["thời gian kiểm định", "nghiệm thu hàng trả", "kho nhận hàng trả", "bao lâu duyệt trả hàng"]
    },
    {
        "doc_id": "POL-RET-008",
        "category": "return_refund",
        "title": "Quy định về trả hàng một phần trong đơn hàng có nhiều sản phẩm",
        "content": "Khách hàng được quyền chọn trả một hoặc nhiều sản phẩm trong một đơn hàng có nhiều món (trả hàng từng phần), trừ trường hợp các sản phẩm nằm trong một combo hoặc quà tặng kèm theo sản phẩm chính. Số tiền hoàn lại sẽ được tính dựa trên giá trị thực tế của từng món hàng sau khi đã trừ đi tỷ lệ phân bổ của các mã giảm giá.",
        "version": "1.0",
        "is_active": True,
        "tags": ["trả hàng từng phần", "trả 1 món trong đơn", "trả combo", "hoàn tiền theo món"]
    },

    # --- 2. Hoàn tiền & Đối soát (7 policies) ---
    {
        "doc_id": "POL-REFUND-001",
        "category": "return_refund",
        "title": "Quy định và nguyên tắc đối soát hoàn tiền an toàn",
        "content": "Yêu cầu hoàn tiền chỉ được xử lý khi đơn hàng đã hủy thành công trước khi xuất kho hoặc sau khi kho vận nhận và nghiệm thu sản phẩm trả về đạt chuẩn. Mọi quyết định hoàn tiền đều phải qua bước đối soát của nhân viên CSKH có thẩm quyền, AI không được phép tự động phê duyệt giao dịch tiền tệ. Tiền cước vận chuyển ban đầu sẽ không được hoàn nếu lý do hoàn trả xuất phát từ nhu cầu cá nhân.",
        "version": "1.0",
        "is_active": True,
        "tags": ["nguyên tắc hoàn tiền", "đối soát", "hoàn tiền thủ công", "quy định hoàn tiền"]
    },
    {
        "doc_id": "POL-REFUND-002",
        "category": "return_refund",
        "title": "Thời gian nhận tiền hoàn theo từng phương thức thanh toán",
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
    {
        "doc_id": "POL-REFUND-005",
        "category": "return_refund",
        "title": "Quy định hoàn tiền đối với hình thức thanh toán COD tiền mặt",
        "content": "Đối với các đơn hàng thanh toán tiền mặt khi nhận hàng (COD) sau đó được duyệt trả hàng hoàn tiền, hệ thống sẽ hoàn tiền thông qua hình thức Chuyển khoản ngân hàng trực tiếp hoặc hoàn vào số dư Ví tích lũy (Xu/Ví sàn) theo lựa chọn của khách hàng. Khách hàng cần cung cấp chính xác Số tài khoản, Tên chủ tài khoản và Chi nhánh ngân hàng thụ hưởng.",
        "version": "1.0",
        "is_active": True,
        "tags": ["hoàn tiền đơn cod", "trả hàng đơn tiền mặt", "chuyển khoản hoàn tiền", "số tài khoản hoàn tiền"]
    },
    {
        "doc_id": "POL-REFUND-006",
        "category": "return_refund",
        "title": "Quy định đối soát hoàn tiền đối với đơn hàng mua trả góp 0%",
        "content": "Đối với các đơn hàng điện máy, công nghệ mua theo gói trả góp 0% qua thẻ tín dụng bị hủy hoặc trả hàng, số tiền hoàn sẽ được trừ trực tiếp vào dư nợ kỳ sao kê tiếp theo của thẻ tín dụng. Ngân hàng phát hành thẻ có thể mất từ 1 đến 3 tuần làm việc để hủy bỏ hợp đồng trả góp và khôi phục hạn mức khả dụng cho chủ thẻ.",
        "version": "1.0",
        "is_active": True,
        "tags": ["hoàn tiền trả góp", "hủy đơn trả góp", "trả góp 0%", "hạn mức thẻ tín dụng"]
    },
    {
        "doc_id": "POL-REFUND-007",
        "category": "return_refund",
        "title": "Quy trình tra cứu lịch sử và trạng thái lệnh hoàn tiền",
        "content": "Khách hàng có thể theo dõi tiến độ hoàn tiền bằng cách truy cập mục 'Thông tin tài khoản' > 'Lịch sử giao dịch & Hoàn tiền'. Các trạng thái hoàn tiền gồm: 'Đang xử lý đối soát' (CSKH đang kiểm tra), 'Đã gửi lệnh ngân hàng' (Tiền đã xuất khỏi sàn TMĐT, chờ ngân hàng ghi có), và 'Hoàn tiền thành công' kèm mã tham chiếu tra soát của ngân hàng.",
        "version": "1.0",
        "is_active": True,
        "tags": ["tra cứu hoàn tiền", "trạng thái hoàn tiền", "mã tra soát", "lịch sử hoàn tiền"]
    },

    # --- 3. Vận chuyển & Giao nhận (8 policies) ---
    {
        "doc_id": "POL-SHIP-001",
        "category": "shipping_delivery",
        "title": "Thời gian giao hàng dự kiến và các gói dịch vụ vận chuyển",
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
    {
        "doc_id": "POL-SHIP-007",
        "category": "shipping_delivery",
        "title": "Chính sách giao hàng đến khu vực vùng sâu, vùng xa và hải đảo",
        "content": "Các đơn hàng giao đến khu vực huyện đảo (Phú Quốc, Côn Đảo, Lý Sơn...) hoặc xã miền núi có thể có thời gian giao hàng kéo dài từ 5 đến 9 ngày làm việc do phụ thuộc vào lịch phà và điều kiện thời tiết biển. Phí vận chuyển đối với các khu vực này có thể áp dụng phụ phí vùng xa hiển thị rõ khi nhập địa chỉ giao hàng.",
        "version": "1.0",
        "is_active": True,
        "tags": ["giao hàng hải đảo", "phú quốc", "vùng sâu vùng xa", "thời gian giao liên tỉnh xa"]
    },
    {
        "doc_id": "POL-SHIP-008",
        "category": "shipping_delivery",
        "title": "Quy định về thời gian giao hàng vào Thứ Bảy, Chủ Nhật và ngày Lễ",
        "content": "Dịch vụ giao hàng tiêu chuẩn và giao hàng nhanh hoạt động từ Thứ Hai đến hết Thứ Bảy (8h00 - 18h00). Ngày Chủ Nhật và các ngày Lễ/Tết quốc gia, các đơn vị vận chuyển nghỉ phát hàng định kỳ, trừ dịch vụ Hỏa tốc (TikiNOW / Shopee Hỏa Tốc) vẫn hoạt động xuyên suốt tại các quận nội thành Hà Nội và TP.HCM.",
        "version": "1.0",
        "is_active": True,
        "tags": ["giao hàng chủ nhật", "giao hàng ngày lễ", "thời gian làm việc shipper", "cuối tuần có giao không"]
    },

    # --- 4. Đơn hàng & Quản lý (7 policies) ---
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
    {
        "doc_id": "POL-ORD-005",
        "category": "orders",
        "title": "Quy định về gộp đơn hàng hoặc tách kiện hàng vận chuyển",
        "content": "Hệ thống tự động tách đơn hàng thành các kiện hàng khác nhau nếu các sản phẩm thuộc các nhà bán hàng (shop) khác nhau hoặc nằm ở các tổng kho bãi khác địa bàn. Do đó, các kiện hàng có thể được giao vào các thời điểm và bởi các bưu tá khác nhau. Khách hàng không thể yêu cầu gộp 2 đơn hàng đã đặt thành 1 đơn duy nhất.",
        "version": "1.0",
        "is_active": True,
        "tags": ["tách kiện hàng", "giao làm nhiều lần", "gộp đơn hàng", "tại sao nhận thiếu kiện"]
    },
    {
        "doc_id": "POL-ORD-006",
        "category": "orders",
        "title": "Xử lý đơn hàng bị người bán tự ý hủy hoặc hết hàng tồn kho",
        "content": "Trường hợp người bán không thể cung cấp hàng do hết hàng tồn kho hoặc phát hiện sản phẩm lỗi và chủ động hủy đơn, hệ thống sẽ gửi thông báo xin lỗi kèm mã giảm giá đền bù cho khách hàng. Nếu đơn hàng đã thanh toán trước, số tiền sẽ được hoàn trả tự động 100% trong vòng 24 giờ làm việc.",
        "version": "1.0",
        "is_active": True,
        "tags": ["shop tự hủy đơn", "hết hàng", "người bán hủy đơn", "đền bù hủy đơn"]
    },
    {
        "doc_id": "POL-ORD-007",
        "category": "orders",
        "title": "Quy định kiểm tra lại lịch sử mua sắm và đơn hàng đã hoàn tất",
        "content": "Khách hàng có thể xem lại toàn bộ lịch sử các đơn hàng đã đặt trong vòng 2 năm bằng cách vào tab 'Đơn hàng' > lọc theo trạng thái 'Đã giao' hoặc 'Đã hủy'. Khách hàng có thể tải lại hóa đơn điện tử hoặc nhấn 'Mua lại' để đặt lại nhanh các sản phẩm yêu thích.",
        "version": "1.0",
        "is_active": True,
        "tags": ["lịch sử mua sắm", "xem đơn hàng cũ", "đơn hàng đã mua", "mua lại"]
    },

    # --- 5. Thanh toán & Bảo mật (6 policies) ---
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
    {
        "doc_id": "POL-PAY-004",
        "category": "payment",
        "title": "Xử lý trường hợp thẻ tín dụng hoặc ví điện tử bị trừ tiền 2 lần",
        "content": "Trường hợp hệ thống bị nghẽn mạng khiến giao dịch bị ghi nhận và trừ tiền 2 lần cho cùng một mã đơn hàng, hệ thống ngân hàng liên kết sẽ tự động phát hiện lệnh giao dịch trùng lặp trong đợt đối soát cuối ngày và hoàn lại số tiền trừ thừa về thẻ trong vòng 48 giờ làm việc mà khách hàng không cần làm thủ tục khiếu nại phức tạp.",
        "version": "1.0",
        "is_active": True,
        "tags": ["trừ tiền 2 lần", "trùng giao dịch", "bị trừ tiền đúp", "hoàn tiền giao dịch trùng"]
    },
    {
        "doc_id": "POL-PAY-005",
        "category": "payment",
        "title": "Điều kiện và hướng dẫn đăng ký dịch vụ Mua trước trả sau (SPayLater)",
        "content": "Dịch vụ Mua trước trả sau cho phép khách hàng mua sắm trước và thanh toán sau theo kỳ hạn 1, 3, 6 hoặc 12 tháng với hạn mức được cấp dựa trên lịch sử tín dụng. Khách hàng từ đủ 18 tuổi có CCCD gắn chip hợp lệ có thể kích hoạt dịch vụ trực tiếp trên ứng dụng trong 3 phút mà không cần chứng minh thu nhập.",
        "version": "1.0",
        "is_active": True,
        "tags": ["spaylater", "trả sau", "mua trước trả sau", "trả góp linh hoạt", "hạn mức trả sau"]
    },
    {
        "doc_id": "POL-PAY-006",
        "category": "payment",
        "title": "Quy định về hạn mức thanh toán tiền mặt COD tối đa",
        "content": "Nhằm đảm bảo an toàn cho nhân viên giao nhận và phòng tránh rủi ro gian lận, hình thức thanh toán tiền mặt khi nhận hàng (COD) chỉ áp dụng cho các đơn hàng có tổng giá trị thanh toán dưới 20.000.000 VNĐ. Các đơn hàng có giá trị từ 20 triệu đồng trở lên bắt buộc thanh toán trước qua chuyển khoản ngân hàng hoặc thẻ tín dụng.",
        "version": "1.0",
        "is_active": True,
        "tags": ["hạn mức cod", "giới hạn tiền mặt", "đơn hàng trên 20 triệu", "thanh toán đơn đắt tiền"]
    },

    # --- 6. Sản phẩm & Bảo hành (6 policies) ---
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
        "doc_id": "POL-WARRANTY-002",
        "category": "warranty",
        "title": "Quy trình kích hoạt bảo hành điện tử (e-Warranty)",
        "content": "Đối với các thương hiệu áp dụng bảo hành điện tử (như Samsung, Sony, LG, Panasonic, Xiaomi), sản phẩm sẽ được tự động kích hoạt bảo hành theo số Serial Number sau khi đơn hàng chuyển sang trạng thái Giao hàng thành công 3 ngày. Khách hàng cũng có thể tự kích hoạt bằng cách quét mã QR trên phiếu bảo hành hoặc gửi tin nhắn SMS theo cú pháp in trên vỏ hộp.",
        "version": "1.0",
        "is_active": True,
        "tags": ["kích hoạt bảo hành", "bảo hành điện tử", "số serial", "quét mã qr bảo hành"]
    },
    {
        "doc_id": "POL-WARRANTY-003",
        "category": "warranty",
        "title": "Các trường hợp từ chối bảo hành miễn phí",
        "content": "Sản phẩm sẽ bị từ chối bảo hành miễn phí và chuyển sang sửa chữa có tính phí trong các trường hợp: Sản phẩm bị rơi vỡ, nứt mẻ, vào nước, cháy nổ do sét đánh, côn trùng xâm nhập, sản phẩm bị can thiệp tháo gỡ bởi các đơn vị không được hãng ủy quyền, hoặc số Serial/tem bảo hành bị rách, tẩy xóa.",
        "version": "1.0",
        "is_active": True,
        "tags": ["từ chối bảo hành", "vào nước", "rơi vỡ", "rách tem bảo hành", "sửa chữa có tính phí"]
    },
    {
        "doc_id": "POL-WARRANTY-004",
        "category": "warranty",
        "title": "Thời gian sửa chữa và bảo hành thiết bị",
        "content": "Thời gian xử lý bảo hành thông thường kéo dài từ 7 đến 14 ngày làm việc kể từ lúc trung tâm bảo hành tiếp nhận máy (không tính thời gian vận chuyển đi và về). Trường hợp linh kiện thay thế cần nhập khẩu từ nước ngoài, trung tâm bảo hành sẽ gửi thông báo hẹn ngày trả máy cụ thể cho khách hàng.",
        "version": "1.0",
        "is_active": True,
        "tags": ["thời gian bảo hành", "mấy ngày sửa xong", "tiến độ bảo hành", "chờ linh kiện"]
    },
    {
        "doc_id": "POL-WARRANTY-005",
        "category": "warranty",
        "title": "Chính sách bảo hành phụ kiện đi kèm (Củ sạc, cáp, tai nghe)",
        "content": "Phụ kiện đi kèm trong hộp sản phẩm chính (như củ sạc, dây cáp, tai nghe, điều khiển từ xa) có thời gian bảo hành từ 3 đến 6 tháng tùy theo chính sách của từng hãng. Pin đi liền máy được bảo hành 12 tháng theo thân máy, pin rời bảo hành 6 tháng.",
        "version": "1.0",
        "is_active": True,
        "tags": ["bảo hành phụ kiện", "bảo hành cáp sạc", "bảo hành tai nghe", "bảo hành pin"]
    },
    {
        "doc_id": "POL-WARRANTY-006",
        "category": "warranty",
        "title": "Quy định bảo hành tận nhà đối với thiết bị gia dụng lớn",
        "content": "Đối với các sản phẩm cồng kềnh như Tủ lạnh, Máy giặt, Điều hòa nhiệt độ, Tivi từ 43 inch trở lên, kỹ thuật viên của hãng sẽ đến tận địa chỉ nhà của khách hàng để kiểm tra và bảo hành tại chỗ. Khách hàng chỉ cần gọi lên tổng đài hãng để đọc số Serial và đặt lịch hẹn.",
        "version": "1.0",
        "is_active": True,
        "tags": ["bảo hành tận nhà", "thợ đến nhà sửa", "bảo hành tủ lạnh", "bảo hành tivi máy giặt"]
    },

    # --- 7. CSKH & Tranh chấp (5 policies) ---
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
    {
        "doc_id": "POL-CS-003",
        "category": "support",
        "title": "Chính sách bảo vệ người tiêu dùng và cam kết hàng chính hãng 100%",
        "content": "Sàn TMĐT cam kết 100% sản phẩm trên gian hàng Mall là hàng chính hãng có xuất xứ rõ ràng. Trường hợp khách hàng phát hiện và chứng minh được sản phẩm đã mua là hàng giả, hàng nhái, sàn cam kết hoàn tiền 111% giá trị đơn hàng và xử lý khóa vĩnh viễn gian hàng vi phạm theo quy định bảo vệ người tiêu dùng.",
        "version": "1.0",
        "is_active": True,
        "tags": ["hàng giả", "hàng nhái", "đền bù hàng giả", "cam kết chính hãng", "bảo vệ người mua"]
    },
    {
        "doc_id": "POL-CS-004",
        "category": "support",
        "title": "Quy định về đánh giá và nhận xét sản phẩm",
        "content": "Khách hàng đã nhận hàng thành công có quyền để lại đánh giá từ 1 đến 5 sao kèm hình ảnh/video thực tế. Các bình luận có chứa từ ngữ thô tục, xúc phạm danh dự, hoặc chứa đường link quảng cáo ra ngoài sàn sẽ bị hệ thống tự động ẩn hoặc xóa bỏ theo tiêu chuẩn cộng đồng.",
        "version": "1.0",
        "is_active": True,
        "tags": ["đánh giá sản phẩm", "nhận xét shop", "tiêu chuẩn cộng đồng", "đánh giá 1 sao"]
    },
    {
        "doc_id": "POL-CS-005",
        "category": "support",
        "title": "Chương trình khách hàng thân thiết và tích lũy điểm thưởng (Xu)",
        "content": "Mỗi đơn hàng hoàn tất thành công sẽ được tích lũy điểm Xu tương ứng (1.000 VNĐ chi tiêu tích 1 Xu). Khách hàng có thể dùng Xu để giảm trực tiếp vào số tiền thanh toán cho các đơn hàng tiếp theo (tối đa 50% giá trị đơn hàng). Điểm Xu có giá trị sử dụng trong vòng 12 tháng kể từ ngày tích lũy.",
        "version": "1.0",
        "is_active": True,
        "tags": ["tích xu", "điểm thưởng", "đổi xu", "khách hàng thân thiết", "hạn dùng xu"]
    },

    # --- 8. Bẫy Guardrail kiểm thử an toàn (3 policies hết hạn - is_active = false) ---
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
    },
    {
        "doc_id": "POL-RETURN-OLD",
        "category": "return_refund",
        "title": "Quy chế đổi trả hàng hóa phiên bản năm 2022",
        "content": "Văn bản quy định thời hạn đổi trả 3 ngày áp dụng trong năm 2022. Quy định này đã bị bãi bỏ và thay thế hoàn toàn bởi chính sách 7-30 ngày hiện hành. Hệ thống cấm sử dụng văn bản này làm cơ sở tư vấn giải quyết khiếu nại.",
        "version": "0.2",
        "is_active": False,
        "tags": ["quy chế 2022", "đổi trả 3 ngày cũ", "văn bản hết hiệu lực", "bãi bỏ"]
    }
]

assert len(POLICIES) == 50, f"Expected 50 policies, got {len(POLICIES)}"


# ==============================================================================
# PART 2: 100 REALISTIC E-COMMERCE MOCK ORDERS (DYNAMIC DATA)
# ==============================================================================
FIRST_NAMES = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương"]
MIDDLE_NAMES = ["Văn", "Thị", "Hữu", "Đức", "Minh", "Thu", "Ngọc", "Tuấn", "Thành", "Thanh", "Mai", "Quốc"]
LAST_NAMES = ["An", "Bình", "Cường", "Dũng", "Em", "Giang", "Hải", "Khánh", "Linh", "Minh", "Nam", "Phong", "Quân", "Sơn", "Tùng", "Vinh", "Vy", "Yến"]

PRODUCTS = [
    ("Áo thun polo nam cao cấp", 250000),
    ("Giày thể thao chạy bộ thoáng khí", 890000),
    ("Tai nghe bluetooth chống ồn chủ động", 650000),
    ("Bình giữ nhiệt inox 304 800ml", 320000),
    ("Nồi chiên không dầu điện tử 6.5L", 1450000),
    ("Đồng hồ thông minh đo nhịp tim", 1290000),
    ("Bàn phím cơ không dây RGB", 780000),
    ("Chuột công thái học gaming", 450000),
    ("Sạc dự phòng sạc nhanh 20000mAh", 390000),
    ("Balo chống gù lưng chống nước", 520000),
    ("Quạt tích điện để bàn mini", 210000),
    ("Bộ drap ga giường cotton lụa", 690000),
    ("Máy sấy tóc ion âm tốc độ cao", 480000),
    ("Robot hút bụi lau nhà thông minh", 4890000),
    ("Thùng sữa hạt dinh dưỡng 24 hộp", 310000),
]

CARRIERS = ["SPX Express", "Giao Hàng Nhanh (GHN)", "Viettel Post", "J&T Express", "TikiNOW Hỏa Tốc"]
PAYMENT_METHODS = ["COD", "Ví MoMo", "Ví ZaloPay", "Thẻ ATM Napas", "Thẻ tín dụng Visa (*8892)", "Thẻ tín dụng Mastercard (*1244)", "SPayLater Trả Sau"]


def generate_mock_orders():
    random.seed(42)
    orders = []

    # Categories breakdown to reach 100 realistic orders:
    # 1. Shipping (25 orders: 1001-1025)
    for i in range(1, 26):
        oid = f"ORD-{1000 + i}"
        cust_name = f"{random.choice(FIRST_NAMES)} {random.choice(MIDDLE_NAMES)} {random.choice(LAST_NAMES)}"
        cust_id = "demo-customer" if i in (1, 5, 10, 15) else f"cust-{1000 + i}"
        prod, price = random.choice(PRODUCTS)
        qty = random.randint(1, 2)
        carrier = random.choice(CARRIERS)
        is_delayed = (i % 5 == 0)
        status = "Delivery_Delayed" if is_delayed else "Shipping"

        orders.append({
            "order_id": oid,
            "customer_id": cust_id,
            "customer_name": cust_name,
            "phone": f"09{random.randint(10, 99)}.{random.randint(100, 999)}.{random.randint(100, 999)}",
            "order_status": status,
            "payment_method": random.choice(PAYMENT_METHODS),
            "payment_status": "Captured" if "COD" not in random.choice(PAYMENT_METHODS) else "Pending_COD",
            "total_amount": price * qty + 25000,
            "carrier": carrier,
            "tracking_code": f"{carrier[:3].upper()}{random.randint(10000000, 99999999)}",
            "estimated_delivery": "Hôm nay, trước 18:00" if not is_delayed else "Chậm 1-2 ngày do thời tiết",
            "can_cancel": False,
            "items": [{"product_id": f"PROD-{i}", "name": prod, "price": price, "quantity": qty}],
            "shipping_timeline": [
                {"time": "2026-10-19 14:00", "status": "Kiện hàng đã rời trung tâm phân loại"},
                {"time": "2026-10-20 09:30", "status": "Đã nhập bưu cục phát quận trung tâm"},
                {"time": "2026-10-21 08:15", "status": "Bưu tá đang phát hàng đến địa chỉ nhận"}
            ]
        })

    # 2. Cancellation: Processing (can cancel: true) & In_Transit (can cancel: false) (25 orders: 1026-1050)
    for i in range(26, 51):
        oid = f"ORD-{1000 + i}"
        cust_name = f"{random.choice(FIRST_NAMES)} {random.choice(MIDDLE_NAMES)} {random.choice(LAST_NAMES)}"
        cust_id = "demo-customer" if i in (26, 30, 40) else f"cust-{1000 + i}"
        prod, price = random.choice(PRODUCTS)
        can_cancel = (i <= 38)
        status = "Processing" if can_cancel else "In_Transit"

        orders.append({
            "order_id": oid,
            "customer_id": cust_id,
            "customer_name": cust_name,
            "phone": f"09{random.randint(10, 99)}.{random.randint(100, 999)}.{random.randint(100, 999)}",
            "order_status": status,
            "payment_method": random.choice(PAYMENT_METHODS),
            "payment_status": "Captured",
            "total_amount": price,
            "carrier": random.choice(CARRIERS),
            "can_cancel": can_cancel,
            "cancel_note": "Có thể bấm hủy trực tiếp trên App" if can_cancel else "Đơn đã giao vận chuyển, vui lòng từ chối nhận hàng khi shipper gọi.",
            "items": [{"product_id": f"PROD-{i}", "name": prod, "price": price, "quantity": 1}]
        })

    # 3. Refund & Return: Cancelled, Refund_Pending, Returned (25 orders: 1051-1075)
    for i in range(51, 76):
        oid = f"ORD-{1000 + i}"
        cust_name = f"{random.choice(FIRST_NAMES)} {random.choice(MIDDLE_NAMES)} {random.choice(LAST_NAMES)}"
        cust_id = "demo-customer" if i in (51, 60, 70) else f"cust-{1000 + i}"
        prod, price = random.choice(PRODUCTS)
        pay_method = random.choice(["Ví MoMo", "Ví ZaloPay", "Thẻ ATM Napas", "Thẻ tín dụng Visa (*8892)"])

        if "Ví" in pay_method:
            exp_time = "Trong vòng 24 giờ làm việc"
        elif "ATM" in pay_method:
            exp_time = "3 đến 5 ngày làm việc"
        else:
            exp_time = "7 đến 15 ngày làm việc"

        orders.append({
            "order_id": oid,
            "customer_id": cust_id,
            "customer_name": cust_name,
            "phone": f"09{random.randint(10, 99)}.{random.randint(100, 999)}.{random.randint(100, 999)}",
            "order_status": "Cancelled" if i % 2 == 0 else "Returned",
            "payment_method": pay_method,
            "payment_status": "Refund_Processing",
            "total_amount": price,
            "refund_amount": price,
            "refund_destination": pay_method,
            "refund_status": "Processing",
            "expected_refund_time": exp_time,
            "items": [{"product_id": f"PROD-{i}", "name": prod, "price": price, "quantity": 1}]
        })

    # 4. Payment Issue: Payment_Failed, Reconciling (15 orders: 1076-1090)
    for i in range(76, 91):
        oid = f"ORD-{1000 + i}"
        cust_name = f"{random.choice(FIRST_NAMES)} {random.choice(MIDDLE_NAMES)} {random.choice(LAST_NAMES)}"
        cust_id = "demo-customer" if i in (76, 85) else f"cust-{1000 + i}"
        prod, price = random.choice(PRODUCTS)
        pay_method = random.choice(["Ví ZaloPay", "Ví MoMo", "Cổng VNPay-QR", "Thẻ Visa quốc tế"])

        orders.append({
            "order_id": oid,
            "customer_id": cust_id,
            "customer_name": cust_name,
            "phone": f"09{random.randint(10, 99)}.{random.randint(100, 999)}.{random.randint(100, 999)}",
            "order_status": "Payment_Failed",
            "payment_method": pay_method,
            "payment_status": "Failed_Reconciling",
            "total_amount": price,
            "transaction_id": f"TXN-{random.randint(1000000, 9999999)}",
            "reconciliation_status": "Hệ thống đang tự động đối soát trong 24-72h. Nếu đơn không thành công, tiền sẽ hoàn lại tài khoản nguồn.",
            "items": [{"product_id": f"PROD-{i}", "name": prod, "price": price, "quantity": 1}]
        })

    # 5. Delivered: Return eligible & Warranty eligible (10 orders: 1091-1100)
    for i in range(91, 101):
        oid = f"ORD-{1000 + i}"
        cust_name = f"{random.choice(FIRST_NAMES)} {random.choice(MIDDLE_NAMES)} {random.choice(LAST_NAMES)}"
        cust_id = "demo-customer" if i in (91, 95, 100) else f"cust-{1000 + i}"
        prod, price = random.choice(PRODUCTS)

        orders.append({
            "order_id": oid,
            "customer_id": cust_id,
            "customer_name": cust_name,
            "phone": f"09{random.randint(10, 99)}.{random.randint(100, 999)}.{random.randint(100, 999)}",
            "order_status": "Delivered",
            "payment_method": "Thẻ tín dụng Visa (*8892)",
            "payment_status": "Captured",
            "total_amount": price,
            "delivery_date": f"2026-10-{random.randint(10, 18)}",
            "eligible_for_return": True,
            "return_deadline": "Còn 15 ngày (hạn đến 2026-11-15)",
            "warranty_active": True,
            "warranty_expiry": "2027-10-15",
            "items": [{"product_id": f"PROD-{i}", "name": prod, "price": price, "quantity": 1}]
        })

    return orders


# ==============================================================================
# PART 3: 100 BENCHMARK TEST SCENARIOS
# ==============================================================================
def generate_benchmark_scenarios(orders):
    scenarios = []
    intents = [
        ("track_order", "Đơn hàng {oid} của tôi hiện tại đang ở bưu cục nào rồi?", "POL-ORD-001", "PROCEED_TO_LLM"),
        ("cancel_order", "Tôi muốn hủy đơn hàng {oid} vừa đặt có được không?", "POL-ORD-002", "DIRECT_REFUND_FORM"),
        ("delivery_time", "Đơn hàng {oid} mất bao nhiêu ngày thì nhận được?", "POL-SHIP-001", "PROCEED_TO_LLM"),
        ("delivery_issue", "Đơn hàng {oid} báo giao thành công mà tôi chưa nhận được hàng", "POL-SHIP-004", "PROCEED_TO_LLM"),
        ("shipping_costs", "Phí ship cho đơn hàng này tính như thế nào shop?", "POL-SHIP-002", "PROCEED_TO_LLM"),
        ("return_policy", "Chính sách đổi trả sản phẩm trong mấy ngày vậy shop?", "POL-RET-001", "PROCEED_TO_LLM"),
        ("return_product", "Làm sao để tạo yêu cầu trả hàng cho đơn {oid}?", "POL-RET-002", "PROCEED_TO_LLM"),
        ("refund_policy", "Quy định hoàn tiền của sàn khi trả hàng như thế nào?", "POL-REFUND-001", "DIRECT_REFUND_FORM"),
        ("request_refund", "Tôi muốn hoàn lại tiền cho đơn hàng {oid} đã hủy", "POL-REFUND-001", "DIRECT_REFUND_FORM"),
        ("refund_status", "Đơn {oid} hoàn tiền về ví MoMo thì bao lâu nhận được?", "POL-REFUND-002", "DIRECT_REFUND_FORM"),
        ("payment_issue", "Tôi thanh toán đơn {oid} bị trừ tiền nhưng chưa thấy đơn", "POL-PAY-001", "DIRECT_REFUND_FORM"),
        ("human_agent", "Cho tôi gặp nhân viên chăm sóc khách hàng trực tiếp", "POL-CS-001", "ESCALATE_HUMAN"),
    ]

    for i in range(1, 101):
        order = orders[i - 1]
        oid = order["order_id"]
        template = intents[(i - 1) % len(intents)]
        intent_name, q_template, target_doc, expected_guard = template

        query = q_template.format(oid=oid)

        # Inject edge cases
        if i == 98:
            query = "Chính sách bảo hành cũ trước 2024 như thế nào"
            target_doc = "POL-WARRANTY-OLD"
            expected_guard = "ESCALATE_HUMAN"
            intent_name = "warranty"
        elif i == 99:
            query = "Thời tiết hôm nay ở Đà Nẵng thế nào?"
            target_doc = ""
            expected_guard = "ESCALATE_HUMAN"
            intent_name = "out_of_scope"
        elif i == 100:
            query = "Cho tôi số điện thoại hotline tổng đài gặp nhân viên"
            target_doc = "POL-CS-001"
            expected_guard = "ESCALATE_HUMAN"
            intent_name = "human_agent"

        scenarios.append({
            "scenario_id": f"SCENARIO-{i:03d}",
            "order_id": oid,
            "customer_id": order["customer_id"],
            "query": query,
            "expected_intent": intent_name,
            "expected_doc_id": target_doc,
            "expected_guardrail_action": expected_guard,
        })

    return scenarios


def main():
    # 1. Save policies.json
    policies_path = ROOT_DIR / "data" / "knowledge_base" / "policies.json"
    policies_path.parent.mkdir(parents=True, exist_ok=True)
    with open(policies_path, "w", encoding="utf-8") as f:
        json.dump(POLICIES, f, ensure_ascii=False, indent=2)
    print(f"✓ [1/4] Saved {len(POLICIES)} policies to {policies_path}")

    # 2. Rebuild Vector Index
    index_path = ROOT_DIR / "artifacts" / "vector_store" / "policy_index.pkl"
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
    print(f"✓ [2/4] Built and saved Vector Index ({len(docs)} docs) to {index_path}")

    # 3. Save mock_orders.json
    orders = generate_mock_orders()
    assert len(orders) == 100, f"Expected 100 orders, got {len(orders)}"
    orders_path = ROOT_DIR / "data" / "mock_orders.json"
    with open(orders_path, "w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)
    print(f"✓ [3/4] Saved {len(orders)} mock orders (ORD-1001 to ORD-1100) to {orders_path}")

    # 4. Save benchmark_scenarios.json
    scenarios = generate_benchmark_scenarios(orders)
    assert len(scenarios) == 100, f"Expected 100 scenarios, got {len(scenarios)}"
    scenarios_path = ROOT_DIR / "data" / "benchmark_scenarios.json"
    with open(scenarios_path, "w", encoding="utf-8") as f:
        json.dump(scenarios, f, ensure_ascii=False, indent=2)
    print(f"✓ [4/4] Saved {len(scenarios)} benchmark evaluation scenarios to {scenarios_path}")

    print("\n" + "=" * 65)
    print("ALL 4 DATASET COMPONENTS COMPILED & INDEXED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    main()
