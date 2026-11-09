"""Policy Management View: Automatic Metadata Filter, Date Editing, and Dynamic is_active Recalculation."""
from datetime import date, datetime
import requests
import streamlit as st


def parse_date_safe(date_str: str):
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str.strip()[:10], fmt).date()
        except Exception:
            pass
    return None


def calculate_active_preview(policy_type: str, eff_date_str: str, exp_date_str: str):
    today = date.today()
    if policy_type == "superseded":
        return False, "Chính sách đã bị thay thế (superseded)."
    eff = parse_date_safe(eff_date_str)
    exp = parse_date_safe(exp_date_str)

    if eff and today < eff:
        return False, f"Chưa đến ngày áp dụng ({eff.strftime('%Y-%m-%d')})."
    if exp and today > exp:
        return False, f"Đã quá hạn ngày {exp.strftime('%Y-%m-%d')}."
    if policy_type == "temporary" and not exp:
        return False, "Chính sách tạm thời bắt buộc có ngày hết hạn."
    return True, "Đang có hiệu lực áp dụng."


def render_policy_view(gateway_url: str):
    st.markdown("### 📋 Quản lý Vòng đời Chính sách & Tài liệu (Module Vanh)")
    st.caption("Trích xuất tự động bằng AI, tự động đối soát mốc ngày để tính `is_active`, đồng bộ CSDL và Vector Store.")

    tab_create, tab_manage = st.tabs(["➕ Trích xuất & Tạo chính sách tự động (AI Filter)", "📚 Danh mục chính sách đang áp dụng"])

    # -------------------------------------------------------------------------
    # TAB 1: AI Filter & Creation
    # -------------------------------------------------------------------------
    with tab_create:
        st.markdown("#### 🤖 1. Trích xuất thông tin tự động từ văn bản thô")
        st.write("Nhân viên chỉ cần dán văn bản chính sách/thông báo mới vào ô dưới đây. Hệ thống AI sẽ tự động nhận diện các trường thông tin và tự tính toán trạng thái hiệu lực.")

        col_input, col_meta = st.columns([3, 1])
        with col_input:
            raw_text = st.text_area(
                "Nội dung văn bản chính sách thô:",
                height=180,
                placeholder="Ví dụ: Chính sách hoàn xu Tết 2026. Áp dụng từ 2026-01-01 đến 2026-02-15 cho mọi đơn hàng thời trang...",
            )
        with col_meta:
            sug_cat = st.selectbox(
                "Gợi ý danh mục:",
                ["Tự động nhận diện", "return_refund", "shipping", "warranty", "payment", "promotions", "account", "support"],
            )
            cat_param = None if sug_cat == "Tự động nhận diện" else sug_cat
            btn_filter = st.button("✨ Phân tích với AI (Filter)", type="primary", use_container_width=True)

        if btn_filter:
            if not raw_text.strip():
                st.warning("Vui lòng nhập văn bản chính sách trước khi bấm phân tích.")
            else:
                with st.spinner("Đang chạy mô hình AI trích xuất thực thể và chuẩn hóa cấu trúc..."):
                    try:
                        resp = requests.post(
                            f"{gateway_url}/api/v1/copilot/policy/filter",
                            json={"raw_text": raw_text, "suggested_category": cat_param},
                            timeout=35.0,
                        )
                        if resp.status_code == 200:
                            st.session_state["filter_preview"] = resp.json()
                            st.success("Trích xuất thông tin thành công!")
                        else:
                            st.error(f"Lỗi trích xuất: {resp.status_code} - {resp.text}")
                    except Exception as e:
                        st.error(f"Không thể kết nối dịch vụ phân tích: {str(e)}")

        # Review & Edit Extracted Policy
        preview = st.session_state.get("filter_preview")
        if preview:
            doc = preview.get("extracted_policy", {})
            st.divider()
            st.markdown("#### 📝 2. Nhân viên đối soát & Chỉnh sửa trước khi lưu")

            for w in preview.get("warnings", []):
                st.info(f"💡 {w}")

            col_f1, col_f2 = st.columns([2, 1])
            with col_f1:
                edit_title = st.text_input("Tiêu đề chính sách:", value=doc.get("title", ""))
                edit_content = st.text_area("Nội dung chuẩn hóa:", value=doc.get("content", ""), height=150)
                edit_tags = st.text_input("Thẻ từ khóa (phân cách bằng dấu phẩy):", value=", ".join(doc.get("tags", [])))

            with col_f2:
                edit_doc_id = st.text_input("Mã định danh (Doc ID):", value=doc.get("doc_id", ""))
                edit_category = st.selectbox(
                    "Danh mục:",
                    ["return_refund", "shipping", "warranty", "payment", "promotions", "account", "support"],
                    index=["return_refund", "shipping", "warranty", "payment", "promotions", "account", "support"].index(
                        doc.get("category", "support") if doc.get("category") in ["return_refund", "shipping", "warranty", "payment", "promotions", "account", "support"] else "support"
                    ),
                )
                edit_type = st.selectbox(
                    "Loại văn bản:",
                    ["permanent", "temporary", "superseded"],
                    index=["permanent", "temporary", "superseded"].index(doc.get("policy_type", "permanent")),
                    help="permanent: Vĩnh viễn | temporary: Có thời hạn | superseded: Đã hết hiệu lực thay thế",
                )
                edit_eff = st.text_input("Ngày hiệu lực (YYYY-MM-DD):", value=doc.get("effective_date") or "")
                edit_exp = st.text_input("Ngày hết hạn (YYYY-MM-DD):", value=doc.get("expiration_date") or "")

                # Instant dynamic is_active calculation preview
                calc_active, calc_reason = calculate_active_preview(edit_type, edit_eff, edit_exp)
                if calc_active:
                    st.success(f"🟢 Trạng thái tự động: **Active (Đang áp dụng)**\n\n*{calc_reason}*")
                else:
                    st.error(f"🔴 Trạng thái tự động: **Inactive (Không áp dụng)**\n\n*{calc_reason}*")

            col_submit, _ = st.columns([2, 3])
            with col_submit:
                if st.button("💾 Xác nhận & Lưu chính sách vào CSDL", type="primary", use_container_width=True):
                    with st.spinner("Đang lưu chính sách và đồng bộ Vector Index..."):
                        try:
                            payload = {
                                "policy": {
                                    "doc_id": edit_doc_id,
                                    "title": edit_title,
                                    "content": edit_content,
                                    "category": edit_category,
                                    "policy_type": edit_type,
                                    "effective_date": edit_eff.strip() or None,
                                    "expiration_date": edit_exp.strip() or None,
                                    "tags": [t.strip() for t in edit_tags.split(",") if t.strip()],
                                    "version": doc.get("version", "1.0"),
                                    "is_active": calc_active,
                                },
                                "performed_by": "Nhân viên CSKH",
                                "reason": f"Tạo chính sách từ AI Filter. Trạng thái tự động: {calc_active}",
                            }
                            resp = requests.post(f"{gateway_url}/api/v1/copilot/policy/create", json=payload, timeout=20.0)
                            if resp.status_code in (200, 201):
                                st.success(f"✅ Đã lưu thành công chính sách [{edit_doc_id}]!")
                                st.session_state["filter_preview"] = None
                                st.rerun()
                            else:
                                st.error(f"Lỗi khi lưu chính sách: {resp.status_code} - {resp.text}")
                        except Exception as e:
                            st.error(f"Lỗi kết nối: {str(e)}")

    # -------------------------------------------------------------------------
    # TAB 2: Manage Existing Policies & Edit Dates
    # -------------------------------------------------------------------------
    with tab_manage:
        col_m1, col_m2 = st.columns([3, 1])
        with col_m1:
            st.markdown("#### 📚 Danh mục chính sách đang lưu trữ trong Knowledge Base")
        with col_m2:
            if st.button("🔄 Quét lại mốc ngày (Auto-Sync)", use_container_width=True):
                with st.spinner("Đang đối soát toàn bộ chính sách với ngày hôm nay..."):
                    try:
                        resp = requests.post(f"{gateway_url}/api/v1/copilot/policies/sync-active-status", timeout=15.0)
                        if resp.status_code == 200:
                            st.success("Đã đồng bộ trạng thái theo mốc ngày hôm nay!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi sync: {e}")

        # Fetch policies from gateway
        policies = []
        try:
            resp = requests.get(f"{gateway_url}/api/v1/copilot/policies", timeout=10.0)
            if resp.status_code == 200:
                policies = resp.json()
        except Exception as e:
            st.error(f"Không thể tải danh sách chính sách: {str(e)}")

        if not policies:
            st.info("Chưa có chính sách nào trong hệ thống.")
        else:
            # Filter bar
            filter_cat = st.selectbox("Lọc theo danh mục:", ["Tất cả"] + list(set(p.get("category") or "Khác" for p in policies)))
            filtered_docs = [p for p in policies if filter_cat == "Tất cả" or (p.get("category") or "Khác") == filter_cat]

            st.write(f"Tổng số: **{len(filtered_docs)}** chính sách.")

            for p in filtered_docs:
                p_id = p.get("doc_id", "")
                p_title = p.get("title", "")
                p_type = p.get("policy_type", "permanent")
                p_active = p.get("is_active", False)
                p_eff = p.get("effective_date") or "N/A"
                p_exp = p.get("expiration_date") or "Vô thời hạn"

                status_badge = "🟢 Đang áp dụng (Active)" if p_active else "🔴 Không áp dụng (Inactive)"
                if p_type == "superseded":
                    status_badge = "⚫ Đã thay thế (Superseded)"

                with st.expander(f"[{p_id}] {p_title} — {status_badge}", expanded=False):
                    col_det1, col_det2 = st.columns([2, 1])
                    with col_det1:
                        st.write(f"**Nội dung:**\n\n{p.get('content')}")
                        st.caption(f"Thẻ: {', '.join(p.get('tags', []))}")
                    with col_det2:
                        st.write(f"• **Danh mục:** `{p.get('category')}`")
                        st.write(f"• **Loại:** `{p_type}`")
                        st.write(f"• **Ngày hiệu lực:** `{p_eff}`")
                        st.write(f"• **Ngày hết hạn:** `{p_exp}`")
                        st.write(f"• **Phiên bản:** `v{p.get('version', '1.0')}`")

                    # Inline Edit Form
                    st.markdown("---")
                    st.markdown(f"##### ✏️ Chỉnh sửa chính sách [{p_id}]")
                    new_eff = st.text_input(f"Ngày hiệu lực mới [{p_id}]:", value=p.get("effective_date") or "", key=f"eff_{p_id}")
                    new_exp = st.text_input(f"Ngày hết hạn mới [{p_id}]:", value=p.get("expiration_date") or "", key=f"exp_{p_id}")
                    new_type = st.selectbox(
                        f"Loại văn bản [{p_id}]:",
                        ["permanent", "temporary", "superseded"],
                        index=["permanent", "temporary", "superseded"].index(p_type if p_type in ["permanent", "temporary", "superseded"] else "permanent"),
                        key=f"type_{p_id}",
                    )

                    # Dynamic status preview on edit
                    preview_active, preview_reason = calculate_active_preview(new_type, new_eff, new_exp)
                    if preview_active:
                        st.success(f"Trạng thái tự động sau khi cập nhật: **Active (Có hiệu lực)** ({preview_reason})")
                    else:
                        st.error(f"Trạng thái tự động sau khi cập nhật: **Inactive (Vô hiệu hóa)** ({preview_reason})")

                    col_act1, col_act2 = st.columns([2, 1])
                    with col_act1:
                        if st.button(f"Cập nhật ngày & Trạng thái [{p_id}]", key=f"btn_upd_{p_id}"):
                            with st.spinner("Đang cập nhật CSDL và tự động tính `is_active`..."):
                                try:
                                    upd_payload = {
                                        "effective_date": new_eff.strip() or None,
                                        "expiration_date": new_exp.strip() or None,
                                        "policy_type": new_type,
                                        "performed_by": "Nhân viên CSKH",
                                        "reason": f"Chỉnh sửa mốc ngày hiệu lực/hết hạn. Trạng thái tự động: {preview_active}",
                                    }
                                    resp = requests.patch(f"{gateway_url}/api/v1/copilot/policies/{p_id}", json=upd_payload, timeout=15.0)
                                    if resp.status_code == 200:
                                        st.success(f"Cập nhật thành công! Trạng thái tự động: {preview_active}")
                                        st.rerun()
                                    else:
                                        st.error(f"Lỗi: {resp.text}")
                                except Exception as e:
                                    st.error(f"Lỗi: {str(e)}")

                    with col_act2:
                        if st.button(f"🗑️ Xóa chính sách [{p_id}]", key=f"btn_del_{p_id}"):
                            with st.spinner("Đang xóa..."):
                                try:
                                    resp = requests.delete(f"{gateway_url}/api/v1/copilot/policies/{p_id}", timeout=15.0)
                                    if resp.status_code == 200:
                                        st.success("Đã xóa chính sách!")
                                        st.rerun()
                                    else:
                                        st.error(f"Lỗi xóa: {resp.text}")
                                except Exception as e:
                                    st.error(f"Lỗi: {str(e)}")

