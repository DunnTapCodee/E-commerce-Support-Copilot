"""Policy Management View: Multi-input AI Filter, File Upload, Master-Detail Layout."""
from datetime import date, datetime
import requests
import streamlit as st


CATEGORIES = ["return_refund", "shipping", "warranty", "payment", "promotions", "account", "support"]
POLICY_TYPES = ["permanent", "temporary", "superseded"]


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


def _init_session():
    if "policy_text_blocks" not in st.session_state:
        st.session_state["policy_text_blocks"] = [""]
    if "filter_preview_list" not in st.session_state:
        st.session_state["filter_preview_list"] = []
    if "selected_policy_idx" not in st.session_state:
        st.session_state["selected_policy_idx"] = 0
    if "saved_indices" not in st.session_state:
        st.session_state["saved_indices"] = set()
    if "input_mode" not in st.session_state:
        st.session_state["input_mode"] = "text"


def _call_bulk_filter(raw_text: str, gateway_url: str, cat_param):
    """Call /filter-bulk endpoint and return list of extracted policy dicts."""
    resp = requests.post(
        f"{gateway_url}/api/v1/copilot/policy/filter-bulk",
        json={"raw_text": raw_text, "suggested_category": cat_param},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()  # List of PolicyFilterResult


def _parse_remote_file(file_obj, gateway_url: str) -> str:
    """Send uploaded file to backend for text extraction."""
    files = {"file": (file_obj.name, file_obj.read(), file_obj.type or "application/octet-stream")}
    resp = requests.post(f"{gateway_url}/api/v1/copilot/policy/parse-file", files=files, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    return data.get("text", "")


def _save_policy(idx: int, gateway_url: str, preview_list: list):
    """Save a single extracted policy to the Knowledge Base."""
    item = preview_list[idx]
    doc = item.get("extracted_policy", {})
    calc_active, _ = calculate_active_preview(
        doc.get("policy_type", "permanent"),
        doc.get("effective_date") or "",
        doc.get("expiration_date") or "",
    )
    payload = {
        "policy": {
            "doc_id": doc.get("doc_id", ""),
            "title": doc.get("title", ""),
            "content": doc.get("content", ""),
            "category": doc.get("category", "support"),
            "policy_type": doc.get("policy_type", "permanent"),
            "effective_date": doc.get("effective_date") or None,
            "expiration_date": doc.get("expiration_date") or None,
            "tags": doc.get("tags", []),
            "version": doc.get("version", "1.0"),
            "is_active": calc_active,
        },
        "performed_by": "Nhân viên CSKH",
        "reason": f"Tạo chính sách từ AI Filter (Bulk). is_active={calc_active}",
    }
    resp = requests.post(f"{gateway_url}/api/v1/copilot/policy/create", json=payload, timeout=20.0)
    resp.raise_for_status()


def _render_detail_panel(idx: int, preview_list: list, gateway_url: str):
    """Render the right-side detail panel for the selected policy."""
    if idx >= len(preview_list):
        st.info("Chọn một chính sách ở danh sách bên trái để xem chi tiết.")
        return

    item = preview_list[idx]
    doc = item.get("extracted_policy", {})
    source_label = item.get("source_label", f"Chính sách {idx + 1}")
    warnings = item.get("warnings", [])
    already_saved = idx in st.session_state.get("saved_indices", set())

    st.markdown(f"**Chi tiết [{idx + 1}/{len(preview_list)}] — {source_label}**")
    st.markdown("---")

    # AI extraction info
    for w in warnings:
        st.info(f"💡 {w}")

    # Editable fields
    col1, col2 = st.columns([3, 2])
    with col1:
        new_title = st.text_input("Tiêu đề chính sách:", value=doc.get("title", ""), key=f"det_title_{idx}")
        new_content = st.text_area("Nội dung chuẩn hóa:", value=doc.get("content", ""), height=150, key=f"det_content_{idx}")
        new_tags_str = st.text_input(
            "Thẻ từ khóa (Tags – phân cách bằng dấu phẩy):",
            value=", ".join(doc.get("tags", [])),
            key=f"det_tags_{idx}",
        )
        # Render tag pills
        raw_tags = [t.strip() for t in new_tags_str.split(",") if t.strip()]
        if raw_tags:
            st.markdown(" ".join([f"`#{t}`" for t in raw_tags]))

    with col2:
        new_doc_id = st.text_input("Mã định danh (Doc ID):", value=doc.get("doc_id", ""), key=f"det_id_{idx}")
        cat_val = doc.get("category", "support")
        cat_idx = CATEGORIES.index(cat_val) if cat_val in CATEGORIES else len(CATEGORIES) - 1
        new_category = st.selectbox("Danh mục:", CATEGORIES, index=cat_idx, key=f"det_cat_{idx}")

        ptype_val = doc.get("policy_type", "permanent")
        ptype_idx = POLICY_TYPES.index(ptype_val) if ptype_val in POLICY_TYPES else 0
        new_ptype = st.selectbox(
            "Loại văn bản:",
            POLICY_TYPES,
            index=ptype_idx,
            format_func=lambda x: {"permanent": "permanent (Vĩnh viễn)", "temporary": "temporary (Tạm thời)", "superseded": "superseded (Hết hiệu lực)"}.get(x, x),
            key=f"det_type_{idx}",
        )

        new_eff = st.text_input("Ngày hiệu lực (YYYY-MM-DD):", value=doc.get("effective_date") or "", key=f"det_eff_{idx}")
        new_exp = st.text_input("Ngày hết hạn (YYYY-MM-DD):", value=doc.get("expiration_date") or "", key=f"det_exp_{idx}")

        calc_active, calc_reason = calculate_active_preview(new_ptype, new_eff, new_exp)
        if calc_active:
            st.success(f"🟢 Trạng thái tự động: **Active (Hiệu lực)**\n\n{calc_reason}")
        else:
            st.warning(f"🔴 Trạng thái tự động: **Inactive**\n\n{calc_reason}")

    st.markdown("---")

    # Update session state with edited values so "Save all" picks them up
    doc["title"] = new_title
    doc["content"] = new_content
    doc["tags"] = raw_tags
    doc["doc_id"] = new_doc_id
    doc["category"] = new_category
    doc["policy_type"] = new_ptype
    doc["effective_date"] = new_eff.strip() or None
    doc["expiration_date"] = new_exp.strip() or None

    # Save button
    if already_saved:
        st.success("✅ Đã lưu vào Knowledge Base")
    else:
        if st.button("💾 Lưu chính sách này vào KB", type="primary", use_container_width=True, key=f"det_save_{idx}"):
            with st.spinner("Đang lưu..."):
                try:
                    _save_policy(idx, gateway_url, preview_list)
                    st.session_state["saved_indices"].add(idx)
                    st.success(f"✅ Đã lưu chính sách [{new_doc_id}] vào Knowledge Base!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi khi lưu: {str(e)}")


def render_policy_view(gateway_url: str):
    _init_session()

    st.markdown("### 📋 Quản lý Vòng đời Chính sách & Tài liệu (Module Vanh)")
    st.caption("Trích xuất tự động bằng AI, tự động đối soát mốc ngày để tính `is_active`, đồng bộ CSDL và Vector Store.")

    tab_create, tab_manage = st.tabs(["➕ Trích xuất & Tạo chính sách tự động (AI Filter)", "📚 Danh mục chính sách đang áp dụng"])

    # =========================================================================
    # TAB 1: AI Filter & Creation (Multi-input + Master-Detail)
    # =========================================================================
    with tab_create:
        st.markdown("#### 🤖 1. Trích xuất thông tin tự động từ văn bản thô")
        st.write("Nhân viên dán văn bản hoặc tải tệp lên. Hệ thống AI sẽ tự động nhận diện và trích xuất từng chính sách riêng biệt.")

        # --- Input mode toggle ---
        mode_col1, mode_col2, _ = st.columns([2, 2, 4])
        with mode_col1:
            if st.button("📄 Dán văn bản thô", use_container_width=True,
                         type="primary" if st.session_state["input_mode"] == "text" else "secondary"):
                st.session_state["input_mode"] = "text"
                st.rerun()
        with mode_col2:
            if st.button("📂 Tải tệp tài liệu", use_container_width=True,
                         type="primary" if st.session_state["input_mode"] == "file" else "secondary"):
                st.session_state["input_mode"] = "file"
                st.rerun()

        st.markdown("---")

        raw_texts_to_extract = []  # list of (label, text) tuples

        # ==== TEXT MODE ====
        if st.session_state["input_mode"] == "text":
            st.markdown("**Nhập nội dung văn bản chính sách thô:**")
            st.caption("Mỗi ô nhập = 1 chính sách. Bấm **＋ Thêm chính sách** để thêm ô mới.")

            blocks = st.session_state["policy_text_blocks"]

            for i, block_text in enumerate(blocks):
                col_label, col_del = st.columns([10, 1])
                with col_label:
                    st.markdown(f"**Chính sách {i + 1}:**")
                with col_del:
                    if len(blocks) > 1:
                        if st.button("🗑️", key=f"del_block_{i}", help="Xóa ô này"):
                            blocks.pop(i)
                            st.session_state["policy_text_blocks"] = blocks
                            st.rerun()

                new_val = st.text_area(
                    label=f"block_{i}",
                    value=block_text,
                    height=120,
                    placeholder=f"Dán nội dung chính sách {i + 1} vào đây...",
                    key=f"block_text_{i}",
                    label_visibility="collapsed",
                )
                blocks[i] = new_val

            st.session_state["policy_text_blocks"] = blocks

            if st.button("＋ Thêm chính sách", key="add_block"):
                st.session_state["policy_text_blocks"].append("")
                st.rerun()

            # Build combined text (separated by ---)
            for i, txt in enumerate(blocks):
                if txt.strip():
                    raw_texts_to_extract.append((f"Chính sách {i + 1}", txt.strip()))

        # ==== FILE MODE ====
        else:
            st.markdown("**Tải lên tệp tài liệu chính sách:**")
            st.caption("Hỗ trợ: .txt, .docx, .pdf, .json, .md, .csv — Có thể chọn nhiều tệp cùng lúc.")

            uploaded_files = st.file_uploader(
                "Chọn tệp",
                type=["txt", "docx", "pdf", "json", "md", "csv"],
                accept_multiple_files=True,
                label_visibility="collapsed",
            )

            if uploaded_files:
                st.info(f"Đã chọn {len(uploaded_files)} tệp: {', '.join(f.name for f in uploaded_files)}")
                raw_texts_to_extract = []  # will be filled after parsing

        # --- Category suggestion ---
        col_cat, col_btn = st.columns([3, 2])
        with col_cat:
            sug_cat = st.selectbox(
                "Gợi ý danh mục:",
                ["Tự động nhận diện"] + CATEGORIES,
                help="Hệ thống AI sẽ tự phát hiện nếu để 'Tự động nhận diện'.",
            )
            cat_param = None if sug_cat == "Tự động nhận diện" else sug_cat

        with col_btn:
            st.markdown("<br>", unsafe_allow_html=True)
            btn_extract = st.button("✨ Trích xuất thông tin", type="primary", use_container_width=True)

        # --- Extraction logic ---
        if btn_extract:
            # File mode: parse files first
            if st.session_state["input_mode"] == "file":
                if not uploaded_files:
                    st.warning("Vui lòng chọn ít nhất một tệp tài liệu trước khi trích xuất.")
                else:
                    raw_texts_to_extract = []
                    with st.spinner("Đang phân tích tệp tài liệu..."):
                        for f in uploaded_files:
                            try:
                                text = _parse_remote_file(f, gateway_url)
                                if text.strip():
                                    raw_texts_to_extract.append((f.name, text))
                                else:
                                    st.warning(f"Không đọc được nội dung từ tệp: {f.name}")
                            except Exception as e:
                                st.error(f"Lỗi phân tích tệp {f.name}: {str(e)}")
            else:
                # Text mode: check at least 1 non-empty block
                if not raw_texts_to_extract:
                    st.warning("Vui lòng nhập ít nhất một đoạn văn bản chính sách trước khi trích xuất.")

            if raw_texts_to_extract:
                # Combine all texts into one payload with --- separator
                combined = "\n\n---\n\n".join(txt for _, txt in raw_texts_to_extract)
                with st.spinner(f"Đang chạy AI trích xuất từ {len(raw_texts_to_extract)} nguồn văn bản..."):
                    try:
                        result_list = _call_bulk_filter(combined, gateway_url, cat_param)
                        # Attach source labels
                        for i, item in enumerate(result_list):
                            if i < len(raw_texts_to_extract):
                                item["source_label"] = raw_texts_to_extract[i][0]
                            else:
                                item["source_label"] = f"Chính sách {i + 1}"
                        st.session_state["filter_preview_list"] = result_list
                        st.session_state["selected_policy_idx"] = 0
                        st.session_state["saved_indices"] = set()
                        st.success(f"✅ Đã trích xuất {len(result_list)} chính sách từ dữ liệu thô!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi trích xuất AI: {str(e)}")

        # =====================================================================
        # RESULTS: Master-Detail Layout
        # =====================================================================
        preview_list = st.session_state.get("filter_preview_list", [])
        if preview_list:
            st.markdown("---")
            saved_count = len(st.session_state.get("saved_indices", set()))
            total = len(preview_list)

            # Toolbar
            tool_col1, tool_col2, tool_col3 = st.columns([4, 2, 2])
            with tool_col1:
                st.markdown(
                    f"**Đã trích xuất {total} chính sách từ dữ liệu thô**  \n"
                    f"Trạng thái: {saved_count}/{total} chính sách đã lưu vào Knowledge Base"
                )
            with tool_col2:
                if st.button("🔄 Nhập đợt khác", use_container_width=True):
                    st.session_state["filter_preview_list"] = []
                    st.session_state["policy_text_blocks"] = [""]
                    st.session_state["saved_indices"] = set()
                    st.rerun()
            with tool_col3:
                unsaved = [i for i in range(total) if i not in st.session_state.get("saved_indices", set())]
                if st.button(f"💾 Lưu tất cả ({len(unsaved)}) vào KB", type="primary", use_container_width=True):
                    errors = []
                    with st.spinner("Đang lưu tất cả chính sách..."):
                        for i in unsaved:
                            try:
                                _save_policy(i, gateway_url, preview_list)
                                st.session_state["saved_indices"].add(i)
                            except Exception as e:
                                errors.append(f"Chính sách {i + 1}: {str(e)}")
                    if errors:
                        st.error("Lỗi khi lưu một số chính sách:\n" + "\n".join(errors))
                    else:
                        st.success(f"✅ Đã lưu tất cả {len(unsaved)} chính sách vào Knowledge Base!")
                    st.rerun()

            # Master-Detail layout: left list | right detail
            st.markdown("#### DANH SÁCH CHÍNH SÁCH CẦN DUYỆT")
            col_list, col_detail = st.columns([2, 3])

            with col_list:
                for i, item in enumerate(preview_list):
                    doc = item.get("extracted_policy", {})
                    source_label = item.get("source_label", f"Chính sách {i + 1}")
                    is_saved = i in st.session_state.get("saved_indices", set())
                    is_selected = i == st.session_state.get("selected_policy_idx", 0)
                    is_active_flag = doc.get("is_active", True)
                    ptype = doc.get("policy_type", "permanent")
                    category = doc.get("category", "")
                    tags = doc.get("tags", [])
                    doc_id = doc.get("doc_id", "")
                    title = doc.get("title", f"Chính sách {i + 1}")

                    # Card styling via container
                    card_style = "border: 2px solid #3B82F6; border-radius: 8px; padding: 10px; margin-bottom: 8px; background: #EFF6FF;" if is_selected else "border: 1px solid #E5E7EB; border-radius: 8px; padding: 10px; margin-bottom: 8px;"
                    with st.container():
                        st.markdown(
                            f"""<div style="{card_style}">
                            <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap; margin-bottom:4px;">
                                <span style="background:#DBEAFE; color:#1E40AF; padding:2px 6px; border-radius:4px; font-size:11px; font-weight:600">{doc_id}</span>
                                <span style="background:#F3F4F6; color:#374151; padding:2px 6px; border-radius:4px; font-size:11px;">{(category or "").upper()}</span>
                                <span style="background:{"#D1FAE5" if is_active_flag else "#FEE2E2"}; color:{"#065F46" if is_active_flag else "#991B1B"}; padding:2px 6px; border-radius:4px; font-size:11px;">{"Active" if is_active_flag else "Inactive"}</span>
                            </div>
                            <div style="font-weight:600; font-size:13px; margin-bottom:4px;">{title}</div>
                            <div style="font-size:11px; color:#6B7280; margin-bottom:4px;">{"&nbsp;".join(f"<span style='background:#F3F4F6;padding:1px 5px;border-radius:3px;'>#{t}</span>" for t in tags[:4])}{" <span>+1</span>" if len(tags) > 4 else ""}</div>
                            </div>""",
                            unsafe_allow_html=True,
                        )

                        btn_col1, btn_col2 = st.columns(2)
                        with btn_col1:
                            view_label = "👁 Đang xem" if is_selected else "👁 Xem chi tiết"
                            if st.button(view_label, key=f"view_{i}", use_container_width=True,
                                         type="primary" if is_selected else "secondary"):
                                st.session_state["selected_policy_idx"] = i
                                st.rerun()
                        with btn_col2:
                            if is_saved:
                                st.button("✅ Đã lưu vào KB", key=f"saved_{i}", disabled=True, use_container_width=True)
                            else:
                                if st.button("💾 Lưu vào KB", key=f"save_{i}", use_container_width=True):
                                    with st.spinner("Đang lưu..."):
                                        try:
                                            _save_policy(i, gateway_url, preview_list)
                                            st.session_state["saved_indices"].add(i)
                                            st.success(f"✅ Đã lưu chính sách {i + 1}!")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Lỗi: {str(e)}")

            with col_detail:
                _render_detail_panel(
                    st.session_state.get("selected_policy_idx", 0),
                    preview_list,
                    gateway_url,
                )

    # =========================================================================
    # TAB 2: Manage Existing Policies
    # =========================================================================
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
                p_tags = p.get("tags", [])

                status_badge = "🟢 Đang áp dụng (Active)" if p_active else "🔴 Không áp dụng (Inactive)"
                if p_type == "superseded":
                    status_badge = "⚫ Đã thay thế (Superseded)"

                with st.expander(f"[{p_id}] {p_title} — {status_badge}", expanded=False):
                    col_det1, col_det2 = st.columns([2, 1])
                    with col_det1:
                        st.write(f"**Nội dung:**\n\n{p.get('content')}")
                        if p_tags:
                            st.markdown("**Thẻ từ khóa:** " + " ".join(f"`#{t}`" for t in p_tags))
                    with col_det2:
                        st.write(f"• **Danh mục:** `{p.get('category')}`")
                        st.write(f"• **Loại:** `{p_type}`")
                        st.write(f"• **Ngày hiệu lực:** `{p_eff}`")
                        st.write(f"• **Ngày hết hạn:** `{p_exp}`")
                        st.write(f"• **Phiên bản:** `v{p.get('version', '1.0')}`")

                    st.markdown("---")
                    st.markdown(f"##### ✏️ Chỉnh sửa chính sách [{p_id}]")
                    new_eff = st.text_input(f"Ngày hiệu lực mới [{p_id}]:", value=p.get("effective_date") or "", key=f"eff_{p_id}")
                    new_exp = st.text_input(f"Ngày hết hạn mới [{p_id}]:", value=p.get("expiration_date") or "", key=f"exp_{p_id}")
                    new_type = st.selectbox(
                        f"Loại văn bản [{p_id}]:",
                        POLICY_TYPES,
                        index=POLICY_TYPES.index(p_type if p_type in POLICY_TYPES else "permanent"),
                        key=f"type_{p_id}",
                    )

                    preview_active, preview_reason = calculate_active_preview(new_type, new_eff, new_exp)
                    if preview_active:
                        st.success(f"Trạng thái sau cập nhật: **Active** ({preview_reason})")
                    else:
                        st.error(f"Trạng thái sau cập nhật: **Inactive** ({preview_reason})")

                    col_act1, col_act2 = st.columns([2, 1])
                    with col_act1:
                        if st.button(f"Cập nhật ngày & Trạng thái [{p_id}]", key=f"btn_upd_{p_id}"):
                            with st.spinner("Đang cập nhật CSDL..."):
                                try:
                                    upd_payload = {
                                        "effective_date": new_eff.strip() or None,
                                        "expiration_date": new_exp.strip() or None,
                                        "policy_type": new_type,
                                        "performed_by": "Nhân viên CSKH",
                                        "reason": f"Chỉnh sửa mốc ngày. Trạng thái: {preview_active}",
                                    }
                                    resp = requests.patch(f"{gateway_url}/api/v1/copilot/policies/{p_id}", json=upd_payload, timeout=15.0)
                                    if resp.status_code == 200:
                                        st.success(f"Cập nhật thành công! Trạng thái: {preview_active}")
                                        st.rerun()
                                    else:
                                        st.error(f"Lỗi: {resp.text}")
                                except Exception as e:
                                    st.error(f"Lỗi: {str(e)}")

                    with col_act2:
                        if st.button(f"🗑️ Xóa [{p_id}]", key=f"btn_del_{p_id}"):
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
