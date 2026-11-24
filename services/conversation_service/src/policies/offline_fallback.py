"""Offline / LLM-Unavailable Fallback Drafts for Conversation Service.

Separated from CopilotDraftEngine so static templates and heuristic branches
only activate when live LLM providers are disabled or unreachable.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class OfflineDraftFallback:
    """Deterministic grounded fallback templates used when LLM generation is unavailable."""

    @staticmethod
    def build_draft(
        user_query: str,
        intent: str,
        facts: Dict[str, Any],
        order_data: Optional[Dict[str, Any]],
        citations: List[Any],
        multi_order_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build a clean, grounded Vietnamese CSKH fallback draft."""
        active_cites = [d for d in citations if getattr(d, "is_active", True)]
        if intent not in ("get_discounts", "promotion_policy", "voucher_promo"):
            filtered_cites = [d for d in active_cites if "PROMO" not in str(getattr(d, "doc_id", "")).upper()]
            if filtered_cites:
                active_cites = filtered_cites
        citation_tags = " ".join([f"[{d.doc_id}]" for d in active_cites])

        if multi_order_context:
            candidates = multi_order_context.get("candidates") or []
            reason = multi_order_context.get("reason", "multiple_customer_orders")
            filter_label = multi_order_context.get("filter_label") or "đang lọc"
            if reason == "status_filter_empty":
                return (
                    f"Dạ em chào anh/chị, em đã kiểm tra toàn bộ đơn hàng trên tài khoản của mình. "
                    f"Hiện tại không có đơn hàng nào ở trạng thái {filter_label} ạ. "
                    f"Anh/chị cần em kiểm tra thêm đơn hàng nào khác không ạ?"
                )
            if candidates:
                lines = []
                for idx, o in enumerate(candidates[:5], 1):
                    oid = o.get("order_id", "N/A")
                    st = o.get("order_status") or o.get("status") or "Đang xử lý"
                    items_txt = ", ".join(it.get("name", "") for it in o.get("items", [])) or "Sản phẩm đặt mua"
                    eta = o.get("promised_delivery_date") or o.get("estimated_delivery")
                    eta_str = f" (dự kiến {eta})" if eta else ""
                    lines.append(f"{idx}. #{oid} ({st}) — {items_txt}{eta_str}")
                list_str = "\n".join(lines)
                if reason == "status_filter":
                    return (
                        f"Dạ em chào anh/chị, em gửi mình danh sách các đơn hàng {filter_label} hiện có trên tài khoản:\n"
                        f"{list_str}\n"
                        f"Anh/chị muốn em kiểm tra chi tiết hoặc hỗ trợ thêm cho mã đơn nào ạ?"
                    )
                if reason.startswith("ambiguous_"):
                    return (
                        f"Dạ em chào anh/chị, em thấy tài khoản mình đang có {len(candidates)} đơn hàng phù hợp với yêu cầu này:\n"
                        f"{list_str}\n"
                        f"Anh/chị vui lòng xác nhận chính xác mã đơn (ví dụ #{candidates[0].get('order_id')}) để em tạo yêu cầu hỗ trợ đúng đơn cho mình nhé ạ!"
                    )
                if reason.startswith("no_eligible_"):
                    return (
                        f"Dạ em chào anh/chị, hiện các đơn hàng gần đây của mình ({', '.join('#' + str(o.get('order_id')) for o in candidates[:4])}) "
                        f"đều không ở trạng thái phù hợp để thao tác trực tiếp.\n"
                        f"{list_str}\n"
                        f"Anh/chị vui lòng cho em biết cụ thể mã đơn cần hỗ trợ để em kiểm tra hướng xử lý cho mình nhé ạ!"
                    )
                return (
                    f"Dạ em chào anh/chị, em thấy tài khoản của mình hiện có {len(candidates)} đơn hàng liên quan:\n"
                    f"{list_str}\n"
                    f"Anh/chị đang muốn kiểm tra chi tiết mã đơn nào để em tra cứu chính xác giúp mình ạ?"
                )

        order_id = facts.get("order_id") or (order_data.get("order_id") if order_data else None)

        if intent in ("track_order", "delivery_time", "order_status", "cancel_order"):
            if order_data:
                amount_str = f"{order_data.get('total_amount', 0):,} VNĐ" if order_data.get("total_amount") else "N/A"
                if any(w in user_query.lower() for w in ["bao nhiêu tiền", "hết bao nhiêu", "tổng tiền", "giá bao nhiêu", "thanh toán bao nhiêu", "bao tien"]):
                    cite_suffix = f" {citation_tags}" if citation_tags else ""
                    return (
                        f"Dạ em chào anh/chị, em đã kiểm tra thông tin đơn hàng {order_id or ''} của mình. "
                        f"Tổng giá trị thanh toán cho đơn hàng là {amount_str} (bao gồm đầy đủ thuế và phụ phí){cite_suffix} ạ. "
                        f"Nếu anh/chị cần em hỗ trợ kiểm tra thêm chi tiết các món trong đơn, cứ nhắn lại cho em nhé!"
                    )

                items_str = ", ".join(
                    f"{it.get('name')} (x{it.get('quantity', 1)})" for it in order_data.get("items", [])
                )
                item_suffix = f" ({items_str})" if items_str else ""
                shipper = order_data.get("shipper_name") or order_data.get("carrier") or "đơn vị vận chuyển"
                phone = f" ({order_data.get('shipper_phone')})" if order_data.get("shipper_phone") else ""
                status = str(order_data.get("order_status") or order_data.get("status") or "Đang xử lý")
                status_upper = status.upper()
                est = order_data.get("promised_delivery_date") or order_data.get("estimated_delivery") or "trong thời gian sớm nhất"
                cite_suffix = f" {citation_tags}" if citation_tags else ""

                if status_upper == "DELIVERED":
                    return (
                        f"Dạ em chào anh/chị, em đã kiểm tra đơn hàng {order_id or ''}{item_suffix} của mình. "
                        f"Đơn hàng này đã được giao thành công (trạng thái: Delivered){cite_suffix} ạ. "
                        f"Nếu anh/chị cần hỗ trợ đổi trả hoặc kiểm tra hóa đơn cho đơn này, mình cứ nhắn em nhé!"
                    )
                if status_upper in {"CANCELLED", "RETURNED", "RETURN_REQUESTED", "RETURN_APPROVED"}:
                    return (
                        f"Dạ em chào anh/chị, em đã kiểm tra đơn hàng {order_id or ''}{item_suffix} của mình. "
                        f"Hiện đơn hàng đang ở trạng thái {status}{cite_suffix} ạ. "
                        f"Anh/chị cần em hỗ trợ kiểm tra thêm thông tin gì về đơn này không ạ?"
                    )
                if status_upper in {"PROCESSING", "PAYMENT_FAILED"}:
                    return (
                        f"Dạ em chào anh/chị, em đã kiểm tra đơn hàng {order_id or ''}{item_suffix} của mình. "
                        f"Hiện đơn hàng đang ở trạng thái {status} (dự kiến giao: {est}){cite_suffix} ạ. "
                        f"Anh/chị cần em hỗ trợ kiểm tra thêm hay cập nhật thông tin cho đơn này không ạ?"
                    )
                if status_upper == "DELIVERY_DELAYED":
                    return (
                        f"Dạ em chào anh/chị, em rất xin lỗi vì đơn hàng {order_id or ''}{item_suffix} hiện đang bị giao trễ "
                        f"so với thời gian dự kiến ({est}) qua {shipper}{phone}{cite_suffix} ạ. "
                        f"Em đã ghi nhận để bộ phận vận chuyển ưu tiên giao sớm nhất cho mình nhé!"
                    )
                return (
                    f"Dạ em chào anh/chị, em đã kiểm tra thông tin đơn hàng {order_id or ''}{item_suffix} của mình. "
                    f"Hiện đơn hàng {status} bởi {shipper}{phone} và dự kiến giao đến mình {est}{cite_suffix} ạ. "
                    f"Anh/chị chú ý giữ điện thoại để nhận hàng giúp em nhé!"
                )
            return (
                "Dạ Tiki chào anh/chị, để em hỗ trợ kiểm tra chi tiết lộ trình đơn hàng cho mình, "
                "Bạn vui lòng cho shop xin mã đơn hàng hoặc thông tin đơn hàng nhé ạ!"
            )

        if intent in ("return_policy", "return_product"):
            return (
                f"Dạ em chào anh/chị, theo chính sách đổi trả của Tiki, quý khách được hỗ trợ đổi trả sản phẩm "
                f"trong vòng 30 ngày kể từ ngày nhận hàng đối với sản phẩm còn nguyên tem mác hoặc có lỗi kỹ thuật {citation_tags or '[POL-RET-001]'} ạ. "
                f"Anh/chị chỉ cần giữ lại hộp và phụ kiện ban đầu, bên em sẽ cho bưu tá đến tận nhà để thu hồi miễn phí cho mình ạ!"
            )

        if intent == "shipping_costs":
            return (
                f"Dạ em chào anh/chị, về cước phí vận chuyển, Tiki áp dụng biểu phí giao hàng tiêu chuẩn "
                f"và hỗ trợ miễn phí vận chuyển cho các đơn hàng đạt giá trị tối thiểu theo quy định {citation_tags or '[POL-SHIP-001]'} ạ. "
                f"Anh/chị có thể áp dụng thêm mã Freeship tại bước thanh toán để được giảm phí ship tối đa nhé!"
            )

        if intent in ("get_discounts", "promotion_policy"):
            return (
                f"Dạ em chào anh/chị, về chính sách ưu đãi cho đơn hàng {order_id or ''}, Tiki hiện hỗ trợ áp dụng đồng thời "
                f"nhiều loại mã ưu đãi bao gồm mã giảm giá từ sàn/nhà bán, mã miễn phí vận chuyển Freeship và điểm tích lũy Tiki Xu {citation_tags or '[POL-PROMO-001]'} ạ. "
                f"Nếu đơn hàng đã chuyển sang trạng thái vận chuyển, các mã giảm giá đã áp dụng sẽ được giữ nguyên theo đơn hàng anh/chị nhé!"
            )

        return (
            f"Dạ em chào anh/chị, em đã kiểm tra thông tin về yêu cầu của mình. "
            f"Dựa trên quy định hiện hành của Tiki {citation_tags or '[POL-INFO]'}, trường hợp này sẽ được hỗ trợ xử lý nhanh chóng. "
            f"Anh/chị hỗ trợ kiểm tra lại thông báo đơn hàng hoặc phản hồi lại nếu cần em hỗ trợ thêm nhé ạ!"
        )
