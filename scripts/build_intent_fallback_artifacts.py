"""Build version-independent bilingual (VI/EN) ML fallback artifacts for Intent Service.

Exports pure JSON + NumPy (.npz) linear artifacts (`NumpyLinearBackend`) and `LanguageRouter`
metadata under `artifacts/models/intent/` without touching legacy `.pkl` files or tying
runtime inference to a specific `scikit-learn` pickle version.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.intent_service.src.normalizer import normalize_vietnamese_query
from services.intent_service.src.pipeline.dataset import (
    OOS_LABEL,
    OUT_OF_SCOPE_SAMPLES,
    SEED_EXAMPLES,
    TARGET_INTENTS,
)
from services.intent_service.src.preprocessing import preprocess
from services.intent_service.src.router import VI_CHARS

ALL_CLASSES = sorted([*TARGET_INTENTS, OOS_LABEL])
TOKEN_PATTERN = r"(?u)\b\w\w+\b"

BITEXT_REMAP = {
    "open_account": "create_account",
    "track_delivery": "track_order",
    "return_product_online": "return_product",
    "return_product_in_store": "return_product",
}

POLICY_CATEGORY_TO_INTENT = {
    "warranty": "warranty",
    "promotions": "get_discounts",
}

DOC_ID_TO_INTENT = {
    "POL-ORD-001": "track_order",
    "POL-ORD-002": "cancel_order",
    "POL-SHIP-001": "delivery_time",
    "POL-SHIP-002": "shipping_costs",
    "POL-SHIP-004": "delivery_issue",
    "POL-RET-001": "return_policy",
    "POL-RET-002": "return_product",
    "POL-RET-004": "return_product",
    "POL-REFUND-001": "refund_policy",
    "POL-REFUND-002": "refund_status",
    "POL-PAY-001": "payment_issue",
    "POL-PAY-004": "payment_issue",
    "POL-CS-001": "human_agent",
    "POL-WARRANTY-001": "warranty",
    "POL-WARRANTY-002": "warranty",
    "POL-CS-005": "get_discounts",
    "POL-PROMO-001": "get_discounts",
}

VI_DOMAIN_CORPUS: list[tuple[str, str]] = [
    # track_order
    ("kiểm tra đơn hàng giúp tôi", "track_order"),
    ("tra cứu hành trình đơn hàng đang vận chuyển", "track_order"),
    ("đơn hàng tôi đặt đang nằm ở kho nào rồi", "track_order"),
    ("xem tình trạng kiện hàng của mình", "track_order"),
    ("mã vận đơn của đơn hàng vừa mua là gì", "track_order"),
    ("tổng mình đã thanh toán bao nhiêu tiền cho các đơn hàng", "track_order"),
    ("kiểm tra danh sách các đơn hàng của tôi", "track_order"),
    # cancel_order
    ("hủy đơn hàng đang chờ xử lý giúp mình", "cancel_order"),
    ("tôi đặt nhầm địa chỉ muốn hủy đơn ngay", "cancel_order"),
    ("không muốn mua nữa làm sao hủy đơn hàng", "cancel_order"),
    ("nhờ shop hủy lệnh đặt hàng vừa tạo", "cancel_order"),
    # delivery_time
    ("đặt hàng hôm nay thì mấy ngày nhận được", "delivery_time"),
    ("thời gian giao hàng dự kiến về Đà Nẵng mất bao lâu", "delivery_time"),
    ("giao hàng hỏa tốc tikinow mấy giờ tới nơi", "delivery_time"),
    ("khi nào bưu tá giao kiện hàng tới nhà tôi", "delivery_time"),
    # delivery_issue
    ("đơn hàng quá ngày dự kiến mà vẫn chưa giao tới", "delivery_issue"),
    ("shipper báo giao thành công nhưng tôi chưa nhận được hàng", "delivery_issue"),
    ("kiện hàng bị giao trễ hẹn nhiều ngày rồi", "delivery_issue"),
    ("bưu tá giao nhầm hàng sang địa chỉ khác", "delivery_issue"),
    # shipping_costs
    ("cước phí vận chuyển liên tỉnh tính bao nhiêu tiền", "shipping_costs"),
    ("đơn bao nhiêu tiền thì được miễn phí vận chuyển freeship", "shipping_costs"),
    ("phí giao hàng tiêu chuẩn nội thành là bao nhiêu", "shipping_costs"),
    ("biểu phí ship hàng cồng kềnh tikipro", "shipping_costs"),
    # return_policy
    ("quy định và điều kiện đổi trả sản phẩm trong bao nhiêu ngày", "return_policy"),
    ("chính sách đổi trả hàng tiki trading có cần nguyên seal không", "return_policy"),
    ("danh mục hàng nào không được áp dụng chính sách đổi trả", "return_policy"),
    ("chính sách trả hàng hoàn tiền khi bóc tem", "return_policy"),
    # return_product
    ("sản phẩm nhận bị móp méo vỡ hộp tôi muốn đổi cái mới", "return_product"),
    ("áo mặc bị chật không vừa size cho mình gửi trả lại hàng", "return_product"),
    ("hàng điện tử bị lỗi phần cứng muốn tạo yêu cầu trả hàng", "return_product"),
    ("cách bấm gửi yêu cầu trả lại sản phẩm trên ứng dụng", "return_product"),
    # refund_policy
    ("quy định thời gian hoàn tiền về thẻ tín dụng và ví điện tử", "refund_policy"),
    ("chính sách hoàn tiền đối với đơn thanh toán tiền mặt cod", "refund_policy"),
    ("hủy đơn trả góp thì chính sách hoàn tiền tính thế nào", "refund_policy"),
    ("nguyên tắc đối soát hoàn tiền của sàn như thế nào", "refund_policy"),
    # request_refund
    ("yêu cầu hoàn lại tiền đơn hàng đã hủy cho tôi ngay", "request_refund"),
    ("tôi muốn nhận lại tiền hoàn vào tài khoản ngân hàng", "request_refund"),
    ("đơn hàng thất lạc hãy hoàn trả tiền lại cho mình", "request_refund"),
    ("làm thủ tục hoàn tiền gấp giúp tôi", "request_refund"),
    # refund_status
    ("tra cứu tiến độ hoàn tiền đã chuyển về ví momo chưa", "refund_status"),
    ("sao quá 5 ngày làm việc mà tiền hoàn vẫn chưa về thẻ", "refund_status"),
    ("kiểm tra lịch sử và trạng thái lệnh hoàn tiền", "refund_status"),
    ("mã tra soát giao dịch tiền hoàn ngân hàng của tôi đâu", "refund_status"),
    # payment_issue
    ("quét mã vnpay bị trừ tiền 2 lần cho một đơn hàng", "payment_issue"),
    ("thẻ ngân hàng bị trừ tiền nhưng đơn vẫn báo lỗi thanh toán", "payment_issue"),
    ("không thanh toán được bằng ví zalopay báo giao dịch thất bại", "payment_issue"),
    ("sự cố trừ tiền đúp trên thẻ tín dụng khi thanh toán", "payment_issue"),
    # human_agent
    ("kết nối trực tiếp với tổng đài viên chăm sóc khách hàng", "human_agent"),
    ("tôi cần nói chuyện với nhân viên người thật ngay bây giờ", "human_agent"),
    ("chuyển cuộc trò chuyện sang chuyên viên hỗ trợ", "human_agent"),
    ("cho mình gặp nhân viên trực tổng đài tư vấn", "human_agent"),
    # warranty
    ("chính sách bảo hành chính hãng tivi tủ lạnh mấy tháng", "warranty"),
    ("hướng dẫn kích hoạt bảo hành điện tử theo số serial", "warranty"),
    ("trung tâm bảo hành sửa chữa thiết bị mất bao nhiêu ngày", "warranty"),
    ("sản phẩm rơi vỡ vào nước có được bảo hành miễn phí không", "warranty"),
    # get_discounts
    ("làm sao săn mã giảm giá voucher khuyến mãi trên sàn", "get_discounts"),
    ("cách dùng điểm thưởng tiki xu để giảm giá đơn hàng", "get_discounts"),
    ("hôm nay có chương trình ưu đãi coupon nào cho khách mới", "get_discounts"),
    ("tại sao không áp dụng được mã giảm giá vào giỏ hàng", "get_discounts"),
    # create_account
    ("hướng dẫn cách tạo tài khoản mua hàng mới bằng số điện thoại", "create_account"),
    ("làm thế nào để đăng ký thành viên mới trên ứng dụng", "create_account"),
    ("mở tài khoản khách hàng cá nhân cần thông tin gì", "create_account"),
    ("các bước đăng ký tài khoản tiki lần đầu", "create_account"),
    # recover_password
    ("tôi quên mật khẩu đăng nhập tài khoản phải lấy lại thế nào", "recover_password"),
    ("hướng dẫn khôi phục mật khẩu qua mã xác thực otp email", "recover_password"),
    ("muốn đổi mật khẩu bảo mật mới cho tài khoản", "recover_password"),
    ("không nhớ mật khẩu vào app nhờ hướng dẫn cấp lại", "recover_password"),
    # out_of_scope (diverse non-ecommerce topics: weather, math, cooking, sports, coding, trivia)
    ("thời tiết hôm nay ở Hà Nội mưa hay nắng thế nào", OOS_LABEL),
    ("dự báo thời tiết ngày mai tại thành phố Hồ Chí Minh", OOS_LABEL),
    ("hướng dẫn công thức nấu phở bò chuẩn vị tại nhà", OOS_LABEL),
    ("giải phương trình bậc hai và tính tích phân hàm số này", OOS_LABEL),
    ("kết quả trận bóng đá ngoại hạng anh tối qua tỷ số bao nhiêu", OOS_LABEL),
    ("viết đoạn code python sắp xếp mảng nhanh quicksort", OOS_LABEL),
    ("thủ đô của nước Úc và Nhật Bản tên là gì", OOS_LABEL),
    ("giá vàng sjc và tỷ giá ngoại tệ hôm nay tăng hay giảm", OOS_LABEL),
    ("tư vấn lịch trình du lịch tự túc Đà Lạt 3 ngày 2 đêm", OOS_LABEL),
    ("kể một câu chuyện cười ngắn giải trí đi bạn", OOS_LABEL),
]

EN_EXTRA_CORPUS: list[tuple[str, str]] = [
    ("what is the warranty period for electronic devices", "warranty"),
    ("how do i claim manufacturer warranty repair", "warranty"),
    ("is water damage covered under product warranty policy", "warranty"),
    ("activate electronic warranty with serial number", "warranty"),
    ("where can i get discount promo codes or vouchers", "get_discounts"),
    ("how to apply coupon code at checkout for discount", "get_discounts"),
    ("are there any promotional offers or loyalty points", "get_discounts"),
    ("my discount voucher is not working on this order", "get_discounts"),
    ("what is the weather forecast in hanoi today", OOS_LABEL),
    ("how to cook beef noodle soup at home", OOS_LABEL),
    ("solve this quadratic equation 2x + 5 = 15", OOS_LABEL),
    ("who won the football match last night", OOS_LABEL),
    ("what is the capital city of france", OOS_LABEL),
    ("write a python function to reverse a linked list", OOS_LABEL),
    ("tell me a funny joke about cats", OOS_LABEL),
    ("stock market index and gold price today", OOS_LABEL),
]


def _prep(text: str) -> str:
    norm, _ = normalize_vietnamese_query(text.strip())
    return preprocess(norm)


def collect_english_dataset() -> tuple[list[str], list[str]]:
    texts: list[str] = []
    labels: list[str] = []

    bitext_csv = ROOT / "data" / "raw" / "Bitext-retail-ecommerce-llm-chatbot-training-dataset" / "bitext-retail-ecommerce-llm-chatbot-training-dataset.csv"
    if bitext_csv.exists():
        df = pd.read_csv(bitext_csv)
        rng = np.random.default_rng(42)
        for raw_intent, group in df.groupby("intent"):
            mapped = BITEXT_REMAP.get(str(raw_intent), str(raw_intent))
            if mapped in TARGET_INTENTS:
                sample_n = min(len(group), 180)
                chosen = group.iloc[rng.choice(len(group), size=sample_n, replace=False)]
                for q in chosen["instruction"].astype(str):
                    clean_q = re.sub(r"\{\{[^}]+\}\}", "ORD-1001", q)
                    texts.append(_prep(clean_q))
                    labels.append(mapped)

    for q, it in SEED_EXAMPLES + OUT_OF_SCOPE_SAMPLES + EN_EXTRA_CORPUS:
        if not VI_CHARS.search(q) and it in ALL_CLASSES:
            for variant in (q, f"please help {q}", f"can you check {q}"):
                texts.append(_prep(variant))
                labels.append(it)

    return texts, labels


def collect_vietnamese_dataset() -> tuple[list[str], list[str]]:
    texts: list[str] = []
    labels: list[str] = []
    seen: set[tuple[str, str]] = set()

    def _add(raw_q: str, intent_label: str) -> None:
        if intent_label not in ALL_CLASSES:
            return
        prepped = _prep(raw_q)
        if prepped and (prepped, intent_label) not in seen:
            seen.add((prepped, intent_label))
            texts.append(prepped)
            labels.append(intent_label)

    for q, it in SEED_EXAMPLES + OUT_OF_SCOPE_SAMPLES + VI_DOMAIN_CORPUS:
        if VI_CHARS.search(q):
            _add(q, it)

    bench_path = ROOT / "data" / "benchmark_scenarios.json"
    if bench_path.exists():
        for row in json.loads(bench_path.read_text(encoding="utf-8")):
            q = str(row.get("query") or "").strip()
            it = str(row.get("expected_intent") or "").strip()
            if q and VI_CHARS.search(q):
                _add(q, it)

    policies_path = ROOT / "data" / "knowledge_base" / "policies.json"
    if policies_path.exists():
        for pol in json.loads(policies_path.read_text(encoding="utf-8")):
            if not pol.get("is_active", True):
                continue
            doc_id = str(pol.get("doc_id") or "")
            it = DOC_ID_TO_INTENT.get(doc_id) or POLICY_CATEGORY_TO_INTENT.get(str(pol.get("category") or ""))
            if it in ALL_CLASSES:
                _add(str(pol["title"]), it)
                for tag in pol.get("tags") or []:
                    if len(str(tag).split()) >= 2:
                        _add(str(tag), it)

    return texts, labels


def fit_and_export_numpy_linear(
    texts: list[str],
    labels: list[str],
    out_dir: Path,
    c_reg: float = 2.5,
    temperature: float = 0.55,
) -> None:
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        token_pattern=TOKEN_PATTERN,
        sublinear_tf=True,
        lowercase=True,
        max_features=12000,
    )
    X = vectorizer.fit_transform(texts)
    clf = LogisticRegression(
        C=c_reg,
        max_iter=1000,
        class_weight="balanced",
        random_state=42,
    )
    clf.fit(X, labels)

    classes = [str(c) for c in clf.classes_]
    if classes != ALL_CLASSES:
        missing = set(ALL_CLASSES) - set(classes)
        raise RuntimeError(f"Missing target classes in {out_dir.name}: {sorted(missing)}")

    out_dir.mkdir(parents=True, exist_ok=True)
    vocab_clean = {str(k): int(v) for k, v in vectorizer.vocabulary_.items()}
    (out_dir / "vocab.json").write_text(
        json.dumps({"vocab": vocab_clean}, ensure_ascii=False),
        encoding="utf-8",
    )
    np.savez_compressed(
        out_dir / "weights.npz",
        idf=np.asarray(vectorizer.idf_, dtype=np.float32),
        coef=np.asarray(clf.coef_, dtype=np.float32),
        intercept=np.asarray(clf.intercept_, dtype=np.float32),
    )
    meta = {
        "backend": "numpy_linear",
        "method": f"tfidf_logreg_numpy_{out_dir.name}",
        "classes": classes,
        "ngram_max": 2,
        "sublinear_tf": True,
        "temperature": temperature,
        "vocab_file": "vocab.json",
        "weights_file": "weights.npz",
        "train_samples": len(texts),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def export_router(out_dir: Path) -> None:
    from services.intent_service.src.router import VI_NOTONE

    router_dir = out_dir / "router"
    router_dir.mkdir(parents=True, exist_ok=True)
    extra_vi_notone = sorted(
        set(VI_NOTONE)
        | {
            "shop",
            "minh",
            "giup",
            "xem",
            "chua",
            "khuyen",
            "mai",
            "bao",
            "hanh",
            "mat",
            "khau",
            "tai",
            "khoan",
            "thoi",
            "tiet",
            "ngay",
            "tien",
            "ship",
        }
    )
    (router_dir / "vi_notone.txt").write_text("\n".join(extra_vi_notone) + "\n", encoding="utf-8")
    (router_dir / "meta.json").write_text(
        json.dumps({"threshold": 0.2, "seed": 42}, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    target_root = ROOT / "artifacts" / "models" / "intent"
    export_router(target_root)

    en_texts, en_labels = collect_english_dataset()
    fit_and_export_numpy_linear(en_texts, en_labels, target_root / "en", c_reg=1.8, temperature=0.80)

    vi_texts, vi_labels = collect_vietnamese_dataset()
    fit_and_export_numpy_linear(vi_texts, vi_labels, target_root / "vi", c_reg=2.2, temperature=1.0)
    print(f"Exported router + EN ({len(en_texts)} rows) + VI ({len(vi_texts)} rows) to {target_root}")


if __name__ == "__main__":
    main()
