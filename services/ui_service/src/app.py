
"""Streamlit CSKH Agent Workbench and Telemetry Dashboard on Port 8501."""
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Optional
import datetime

import pandas as pd
import requests
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="AI Customer Support Copilot Workbench",
    page_icon="🛍️",
    layout="wide",
)

st.title("🛍️ AI Customer Support Copilot Workbench")
st.caption(
    "Distributed Microservices Architecture · "
    "Single Gateway Point (Port 8000)"
)

# Initialize session state.
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "current_response" not in st.session_state:
    st.session_state.current_response = None

if "request_started" not in st.session_state:
    st.session_state.request_started = None

if "review_started_at" not in st.session_state:
    st.session_state.review_started_at = None

if "review_started_interaction_id" not in st.session_state:
    st.session_state.review_started_interaction_id = None

if "recorded_actions" not in st.session_state:
    st.session_state.recorded_actions = {}

tab1, tab2, tab3 = st.tabs(
    ["💬 Agent Workbench", "📊 Audit & Analytics Dashboard", "📜 Quản lý Chính sách"]
)

# ====================================================================
# TAB 1: CSKH Agent Workbench
# ====================================================================
with tab1:
    left_col, right_col = st.columns(2, gap="large")

    with left_col:
        st.subheader("Hộp thoại tiếp nhận yêu cầu")

        with st.form("cskh_inquiry_form"):
            user_query = st.text_area(
                "Nội dung tin nhắn khách hàng",
                placeholder=(
                    "Ví dụ: Tôi muốn hỏi về thời gian giao hàng "
                    "hoặc chính sách đổi trả..."
                ),
                height=140,
            )
            customer_account = st.text_input(
                "Mã định danh khách hàng (Customer ID)",
                value="demo-customer",
            )
            submit_btn = st.form_submit_button(
                "⚡ Phân tích & Tạo nháp",
                type="primary",
                use_container_width=True,
            )

        if submit_btn:
            if not user_query.strip():
                st.warning("Vui lòng nhập nội dung câu hỏi.")
            else:
                st.session_state.request_started = time.perf_counter()

                payload = {
                    "query": user_query.strip(),
                    "session_id": st.session_state.session_id,
                    "customer_id": customer_account.strip() or None,
                }

                try:
                    with st.spinner("Gateway đang điều phối phân tích..."):
                        res = requests.post(
                            f"{GATEWAY_URL}/api/v1/copilot/query",
                            json=payload,
                            timeout=15,
                        )

                    if res.status_code == 200:
                        st.session_state.current_response = res.json()

                        # Bắt đầu tính thời gian kiểm duyệt riêng cho
                        # interaction mới, không tính thời gian chờ Gateway.
                        st.session_state.review_started_at = time.perf_counter()
                        st.session_state.review_started_interaction_id = (
                            st.session_state.current_response.get(
                                "interaction_id"
                            )
                        )
                    else:
                        st.error(
                            f"Gateway trả về lỗi ({res.status_code}): "
                            f"{res.text}"
                        )
                except requests.RequestException as exc:
                    st.error(
                        f"Không thể kết nối đến Gateway "
                        f"({GATEWAY_URL}): {exc}"
                    )

    # Load current response once for both columns.
    resp = st.session_state.current_response

    if resp:
        interaction_id = resp.get("interaction_id")
        intent_info = resp.get("intent", {})
        guard_info = resp.get("guardrail", {})
        citations = resp.get("citations", [])
        draft_text = resp.get("draft_text", "")
        order_data = resp.get("order_data")
        generation_mode = resp.get("generation_mode", "unknown")

        # Initialize review timer if an existing response is restored
        # without its timer state.
        if (
            st.session_state.review_started_interaction_id != interaction_id
        ):
            st.session_state.review_started_at = time.perf_counter()
            st.session_state.review_started_interaction_id = interaction_id

        with left_col:
            st.markdown("---")
            st.subheader("🔍 Thông tin kiểm tra và kết quả thẩm định")

            c1, c2, c3 = st.columns(3)

            with c1:
                st.metric(
                    "Ý định dự đoán",
                    intent_info.get("intent", "N/A"),
                )

            with c2:
                confidence = intent_info.get("confidence", 0.0)
                st.metric("Confidence", f"{confidence:.1%}")

            with c3:
                guard_action = guard_info.get("action_type", "UNKNOWN")
                st.metric("Trạng thái Guardrail", guard_action)

            st.write(
                f"**Lý do quyết định:** "
                f"{guard_info.get('reason', '')}"
            )
            st.write(
                "**Cho phép gọi LLM:** "
                f"{'✅ Có' if guard_info.get('allow_llm') else '🚫 Không'}"
            )

            # Show top candidate intents.
            probabilities = intent_info.get("all_probabilities", {})
            if probabilities:
                with st.expander("Phân phối xác suất Intent (Top 5)"):
                    sorted_probabilities = sorted(
                        probabilities.items(),
                        key=lambda item: item[1],
                        reverse=True,
                    )[:5]

                    probability_df = pd.DataFrame(
                        sorted_probabilities,
                        columns=["Intent", "Probability"],
                    )
                    st.dataframe(
                        probability_df,
                        use_container_width=True,
                    )

            # Display retrieved policy documents.
            st.subheader("📚 Tài liệu chính sách trích dẫn")

            if citations:
                for doc in citations:
                    is_active = doc.get("is_active", False)
                    status_badge = (
                        "🟢 Hiệu lực"
                        if is_active
                        else "🔴 HẾT HIỆU LỰC"
                    )

                    st.markdown(
                        f"- **[{doc.get('doc_id')}] "
                        f"{doc.get('title')}** "
                        f"(v{doc.get('version')}) · {status_badge}"
                    )

                    with st.expander(
                        f"Xem nội dung trích lục: {doc.get('doc_id')}"
                    ):
                        st.write(doc.get("content", ""))
            else:
                st.info("Không có tài liệu trích dẫn nào được sử dụng.")

        # ------------------------------------------------------------
        # Right column: Draft review and human decision recording.
        # ------------------------------------------------------------
        with right_col:
            st.subheader("📝 Phản hồi của nhân viên")

            if generation_mode == "gemini":
                st.info(
                    "Bản nháp được tạo bởi Gemini. "
                    "Nhân viên cần kiểm tra trước khi sử dụng."
                )
            elif generation_mode == "template_fallback":
                st.warning(
                    "Hệ thống đang sử dụng bản nháp dự phòng. "
                    "Nhân viên cần kiểm tra kỹ trước khi sử dụng."
                )
            elif generation_mode == "not_generated":
                st.warning(
                    "Hệ thống không tạo bản nháp tự động; "
                    "cần nhân viên xử lý."
                )
            else:
                st.info("Chưa xác định được phương thức tạo bản nháp.")

            if order_data:
                st.warning(
                    "⚠️ Có dữ liệu đơn hàng cần được đối soát "
                    "trước khi phản hồi."
                )
                st.json(order_data)

            edited_text = st.text_area(
                "Nội dung cuối cùng sau khi nhân viên kiểm tra:",
                value=draft_text,
                height=260,
                key=f"edit_box_{interaction_id}",
            )

            agent_notes = st.text_input(
                "Ghi chú của nhân viên CSKH (không bắt buộc):",
                key=f"notes_{interaction_id}",
            )

            st.caption(
                "Các thao tác bên dưới chỉ ghi nhận quyết định kiểm duyệt "
                "vào hệ thống. Chúng không gửi tin nhắn đến khách hàng "
                "và không tự động thực hiện hoàn tiền hoặc thay đổi đơn hàng."
            )

            # Only drafts that passed all Gateway guardrails can be
            # approved or edited as proposed customer responses.
            can_approve_or_edit = (
                guard_action == "PROCEED_TO_LLM"
                and generation_mode in {"gemini", "template_fallback"}
            )

            if not can_approve_or_edit:
                st.warning(
                    "Guardrail yêu cầu xử lý thủ công hoặc chuyển cấp. "
                    "Không thể ghi nhận duyệt/chỉnh sửa bản nháp như "
                    "một phản hồi thông thường. Hãy chọn từ chối "
                    "hoặc chuyển cấp."
                )

            # Avoid recording multiple decisions for the same interaction
            # from this UI session.
            recorded_action = st.session_state.recorded_actions.get(
                interaction_id
            )

            if recorded_action:
                st.success(
                    f"Tương tác này đã ghi nhận quyết định: "
                    f"{recorded_action}."
                )

            col_a, col_b = st.columns(2)
            col_c, col_d = st.columns(2)

            def submit_human_action(
                action_type: str,
                text_payload: Optional[str],
            ):
                """Record the agent's decision; never send to the customer."""
                if (
                    action_type in {"APPROVE", "EDIT"}
                    and not can_approve_or_edit
                ):
                    st.error(
                        "Guardrail chưa cho phép duyệt hoặc chỉnh sửa "
                        "bản nháp này."
                    )
                    return

                if action_type in {"APPROVE", "EDIT"}:
                    if not text_payload or not text_payload.strip():
                        st.warning(
                            "Nội dung cuối cùng không được để trống."
                        )
                        return

                    text_payload = text_payload.strip()
                else:
                    # Reject/escalate do not need customer-facing text.
                    text_payload = None

                review_started_at = st.session_state.review_started_at
                handling_time_ms = (
                    int(
                        (time.perf_counter() - review_started_at) * 1000
                    )
                    if review_started_at is not None
                    else 0
                )

                action_payload = {
                    "interaction_id": interaction_id,
                    "action": action_type,
                    "final_text": text_payload,
                    "agent_notes": agent_notes.strip() or None,
                    "handling_time_ms": handling_time_ms,
                }

                try:
                    action_res = requests.post(
                        f"{GATEWAY_URL}/api/v1/copilot/action",
                        json=action_payload,
                        timeout=5,
                    )

                    if action_res.status_code in (200, 201):
                        st.session_state.recorded_actions[
                            interaction_id
                        ] = action_type

                        st.success(
                            f"Đã ghi nhận quyết định **{action_type}** "
                            f"vào audit log "
                            f"({handling_time_ms} ms). "
                            "Tin nhắn chưa được gửi đến khách hàng."
                        )
                        st.rerun()
                    else:
                        st.error(
                            f"Lỗi ghi nhận quyết định "
                            f"({action_res.status_code}): "
                            f"{action_res.text}"
                        )

                except requests.RequestException as exc:
                    st.error(f"Không thể ghi nhận quyết định: {exc}")

            action_already_recorded = bool(recorded_action)

            if col_a.button(
                "✅ Duyệt bản nháp (ghi log)",
                type="primary",
                use_container_width=True,
                disabled=(
                    action_already_recorded or not can_approve_or_edit
                ),
            ):
                submit_human_action("APPROVE", edited_text)

            if col_b.button(
                "✏️ Ghi nhận chỉnh sửa",
                use_container_width=True,
                disabled=(
                    action_already_recorded or not can_approve_or_edit
                ),
            ):
                submit_human_action("EDIT", edited_text)

            if col_c.button(
                "❌ Từ chối bản nháp",
                use_container_width=True,
                disabled=action_already_recorded,
            ):
                submit_human_action("REJECT", None)

            if col_d.button(
                "🚨 Chuyển cấp trên",
                use_container_width=True,
                disabled=action_already_recorded,
            ):
                submit_human_action("ESCALATE", None)

# ====================================================================
# TAB 2: Audit & Analytics Dashboard
# ====================================================================
with tab2:
    st.subheader("📈 Telemetry & Operational Analytics")

    if st.button("🔄 Làm mới dữ liệu", type="secondary"):
        st.rerun()

    try:
        stats_res = requests.get(
            f"{GATEWAY_URL}/api/v1/copilot/stats",
            timeout=5,
        )

        if stats_res.status_code == 200:
            stats = stats_res.json()

            total_logs = stats.get("total_interactions", 0)
            average_latency = stats.get("average_latency_ms", 0.0)
            actions_breakdown = stats.get("actions_breakdown", {})
            recent_logs = stats.get("recent_records", [])

            total_actions = sum(actions_breakdown.values())
            approved_count = actions_breakdown.get("APPROVE", 0)
            approval_rate = (
                approved_count / total_actions * 100
                if total_actions
                else 0.0
            )

            safety_block_rate = stats.get("safety_block_rate", 100.0)
            false_escalation_rate = stats.get("false_escalation_rate", 0.0)
            guardrail_breakdown = stats.get("guardrail_breakdown", {})

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Tổng tương tác", total_logs)
            m2.metric(
                "Thời gian xử lý TB",
                f"{average_latency:.1f} ms",
            )
            m3.metric("Số quyết định đã ghi nhận", total_actions)
            m4.metric(
                "Tỷ lệ quyết định duyệt",
                f"{approval_rate:.1f}%",
            )

            st.markdown("---")
            st.subheader("🛡️ Module 4 AI Safety Metrics")
            s1, s2, s3 = st.columns(3)
            s1.metric(
                "Tỷ lệ Chặn Truy Vấn Nguy Hại",
                f"{safety_block_rate:.1f}%",
                help="Mục tiêu: 100%. Chặn thành công tác vụ tài chính, bẫy chính sách cũ, out-of-scope, ảo giác.",
            )
            s2.metric(
                "Tỷ lệ Chuyển Người Thật Sai",
                f"{false_escalation_rate:.1f}%",
                help="Mục tiêu: < 5%. Tỷ lệ chuyển cấp sai đối với các câu hỏi hợp lệ trong phạm vi.",
            )
            total_guards = sum(guardrail_breakdown.values())
            proceed_llm_count = guardrail_breakdown.get("PROCEED_TO_LLM", 0)
            llm_throughput = (proceed_llm_count / total_guards * 100) if total_guards else 0.0
            s3.metric(
                "Tỷ lệ cho phép gọi LLM",
                f"{llm_throughput:.1f}%",
                help="Tỷ lệ yêu cầu hợp lệ được phép tạo nháp tự động.",
            )

            st.markdown("---")
            chart_col, table_col = st.columns([1, 2])

            with chart_col:
                st.subheader("Phân bổ hành động nhân viên")

                if actions_breakdown:
                    actions_df = pd.DataFrame(
                        list(actions_breakdown.items()),
                        columns=["Hành động", "Số lượng"],
                    )
                    st.bar_chart(
                        actions_df.set_index("Hành động")
                    )
                else:
                    st.info(
                        "Chưa có hành động kiểm duyệt nào được ghi lại."
                    )

            with table_col:
                st.subheader("Nhật ký tương tác gần nhất")

                if recent_logs:
                    logs_df = pd.DataFrame(recent_logs)

                    display_columns = [
                        "interaction_id",
                        "timestamp",
                        "customer_query",
                        "predicted_intent",
                        "guardrail_action",
                        "human_action",
                        "latency_ms",
                    ]

                    available_columns = [
                        column
                        for column in display_columns
                        if column in logs_df.columns
                    ]

                    st.dataframe(
                        logs_df[available_columns],
                        use_container_width=True,
                        height=350,
                    )
                else:
                    st.info(
                        "Chưa có bản ghi tương tác nào trong cơ sở dữ liệu."
                    )

        else:
            st.error(
                f"Không thể lấy thống kê từ Gateway: {stats_res.text}"
            )

    except requests.RequestException as exc:
        st.warning(
            f"Chưa kết nối được với Telemetry Service qua Gateway: {exc}"
        )

# ====================================================================
# TAB 3: Quản lý Chính sách (LLM-powered extraction)
# ====================================================================

def _compute_is_active(ptype: str, eff_raw, exp_raw, check_date: datetime.date):
    """
    Tính trạng thái isActive dựa trên loại chính sách và ngày kiểm tra.
    - permanent : hoạt động kể từ effective_date (nếu có), không có ngày kết thúc.
    - temporary : hoạt động trong khoảng [effective_date, expiration_date].
    - superseded: nếu có khoảng [effective_date, expiration_date], hoạt động trong khoảng đó;
                  sau expiration_date sẽ là không hoạt động (đã bị thay thế).
    Trả về (is_active: bool, reason: str)
    """
    try:
        eff = datetime.date.fromisoformat(eff_raw) if eff_raw else None
    except Exception:
        eff = None
    try:
        exp = datetime.date.fromisoformat(exp_raw) if exp_raw else None
    except Exception:
        exp = None

    if ptype == "superseded":
        if eff and exp:
            if eff <= check_date <= exp:
                return True, f"superseded — hiệu lực giai đoạn {eff} → {exp}"
            elif check_date > exp:
                return False, f"superseded — đã bị thay thế sau ngày {exp}"
            else:
                return False, f"superseded — chưa bắt đầu (từ {eff})"
        elif exp:
            if check_date <= exp:
                return True, f"superseded — hiệu lực đến {exp}"
            return False, f"superseded — đã bị thay thế từ {exp}"
        return False, "superseded — đã bị thay thế"

    if ptype == "permanent":
        if eff:
            active = check_date >= eff
            return active, f"permanent từ {eff}" if active else f"permanent — chưa có hiệu lực (bắt đầu từ {eff})"
        return True, "permanent (không có ngày bắt đầu — luôn hoạt động)"

    # temporary
    if eff and exp:
        active = eff <= check_date <= exp
        if active:
            return True, f"temporary ({eff} → {exp})"
        elif check_date < eff:
            return False, f"temporary — chưa bắt đầu (từ {eff})"
        else:
            return False, f"temporary — đã kết thúc vào {exp}"
    if eff:
        active = check_date >= eff
        return active, f"temporary từ {eff}" if active else f"temporary — chưa bắt đầu (từ {eff})"
    return False, "temporary — thiếu ngày hiệu lực"


with tab3:
    st.subheader("📜 Quản lý Chính sách")

    col_staff1, col_staff2 = st.columns([2, 1])
    with col_staff1:
        staff_input = st.text_input(
            "👤 Tên / Mã nhân viên phụ trách",
            value=st.session_state.get("staff_name", "NV_CSKH_01"),
            help="Tên nhân viên sẽ được gắn vào Audit Log khi thêm, sửa hoặc khôi phục chính sách.",
            key="tab3_staff_name_input",
        )
        if staff_input:
            st.session_state["staff_name"] = staff_input.strip()
    with col_staff2:
        st.caption("ℹ️ Mọi hành vi cập nhật đều được ghi vết và hỗ trợ khôi phục (Rollback).")

    # ----------------------------------------------------------------
    # SECTION A: kiểm tra isActive toàn bộ Knowledge Base
    # ----------------------------------------------------------------
    with st.expander("🔍 Kiểm tra isActive toàn bộ Knowledge Base", expanded=True):
        st.caption(
            "Chọn một ngày kiểm tra để xem chính sách nào đang **hoạt động** "
            "hay **không hoạt động** tại thời điểm đó."
        )

        check_date = st.date_input(
            "📅 Ngày kiểm tra",
            value=datetime.date.today(),
            key="kb_check_date",
        )

        if st.button("🔄 Tải & Kiểm tra tất cả chính sách"):
            try:
                kb_res = requests.get(
                    f"{GATEWAY_URL}/api/v1/copilot/policies",
                    timeout=15,
                )
                if kb_res.status_code == 200:
                    st.session_state["kb_policies"] = kb_res.json()
                else:
                    st.error(f"Không thể tải KB ({kb_res.status_code}): {kb_res.text}")
            except requests.RequestException as exc:
                st.error(f"Lỗi kết nối: {exc}")

        kb_policies = st.session_state.get("kb_policies", [])
        if kb_policies:
            rows = []
            for p in kb_policies:
                ptype = p.get("policy_type", "permanent")
                eff_raw = p.get("effective_date")
                exp_raw = p.get("expiration_date")
                is_active, reason = _compute_is_active(ptype, eff_raw, exp_raw, check_date)
                rows.append({
                    "ID": p.get("doc_id", ""),
                    "Tiêu đề": p.get("title", ""),
                    "Loại": ptype,
                    "Ngày bắt đầu": eff_raw or "—",
                    "Ngày kết thúc": exp_raw or "—",
                    "isActive": "🟢 Hoạt động" if is_active else "🔴 Không hoạt động",
                    "Lý do": reason,
                })

            df = pd.DataFrame(rows)
            active_count = sum(1 for r in rows if "🟢" in r["isActive"])
            inactive_count = len(rows) - active_count

            c1, c2, c3 = st.columns(3)
            c1.metric("Tổng số chính sách", len(rows))
            c2.metric("🟢 Đang hoạt động", active_count)
            c3.metric("🔴 Không hoạt động", inactive_count)

            st.dataframe(df, use_container_width=True, height=380)
        else:
            st.info("Nhấn **Tải & Kiểm tra** để xem danh sách chính sách trong KB.")

    st.markdown("---")
    # ----------------------------------------------------------------
    # SECTION B: Thêm chính sách mới (LLM extraction)
    # ----------------------------------------------------------------
    st.markdown("### ➕ Thêm chính sách mới")
    st.caption(
        "Nhập văn bản chính sách thô. Hệ thống sẽ dùng Gemini LLM "
        "để tự động trích xuất các trường cấu trúc."
    )

    with st.expander("🔑 Cấu hình Gemini API Key (cho tính năng LLM)", expanded=False):
        user_key = st.text_input(
            "Google Gemini API Key",
            value=st.session_state.get("custom_gemini_key", ""),
            type="password",
            placeholder="Nhập Gemini API Key (AQ... hoặc AIzaSy...)",
            help="Nhập Gemini API Key của bạn để sử dụng mô hình LLM trích xuất chính sách tự động.",
            key="custom_gemini_key_input",
        )
        if user_key:
            st.session_state["custom_gemini_key"] = user_key.strip()

    raw_policy = st.text_area(
        "Nhập quy tắc chính sách thô (định dạng tự do)",
        height=180,
        placeholder=(
            "Ví dụ: Chính sách đổi trả — Khách hàng có quyền đổi trả "
            "trong 30 ngày kể từ ngày nhận hàng..."
        ),
        help="Nhập nguyên văn chính sách, LLM sẽ tự động trích xuất các trường.",
        key="raw_policy_input",
    )

    if st.button("🔎 Chuẩn hoá nội dung (LLM)"):
        if raw_policy.strip():
            with st.spinner("Đang gọi Gemini để trích xuất thông tin..."):
                try:
                    payload = {
                        "raw_text": raw_policy,
                        "gemini_api_key": st.session_state.get("custom_gemini_key", "").strip() or None,
                    }
                    res = requests.post(
                        f"{GATEWAY_URL}/api/v1/copilot/policy/filter",
                        json=payload,
                        timeout=40,
                    )
                    if res.status_code == 200:
                        st.session_state.policy_parsed = res.json()
                    else:
                        try:
                            err_detail = res.json().get("detail", res.text)
                        except Exception:
                            err_detail = res.text
                        st.error(f"❌ Lỗi phân tích chính sách ({res.status_code}): {err_detail}")
                        if res.status_code in (500, 502, 503):
                            st.warning(
                                "💡 **Gợi ý khắc phục:** Kiểm tra xem hệ thống Backend có đang chạy hay không. "
                                "Nếu vừa khởi động lại máy/IDE, hãy mở terminal chạy lệnh `python run_dev.py` "
                                "để khởi động đồng thời Gateway (8000) và RAG Service (8002)."
                            )
                except requests.RequestException as exc:
                    st.error(f"Không thể kết nối đến Gateway ({GATEWAY_URL}): {exc}")
                    st.warning("💡 Vui lòng đảm bảo hệ thống đã được khởi động bằng lệnh: `python run_dev.py`")
        else:
            st.warning("Vui lòng nhập nội dung chính sách.")

    # Show parsed result if available
    if st.session_state.get("policy_parsed"):
        parsed = st.session_state.policy_parsed
        ep = parsed.get("extracted_policy") or {}
        extraction_warnings = parsed.get("warnings", [])
        confidence = parsed.get("confidence_score", 0.0)

        # Remove date-related warnings as requested
        filtered_warnings = [
            w for w in extraction_warnings
            if "ngày hiệu lực" not in w.lower() and "ngày hết hạn" not in w.lower()
        ]
        if filtered_warnings:
            for w in filtered_warnings:
                st.warning(f"⚠️ {w}")
        st.info(f"🎯 Độ tin cậy trích xuất: **{confidence:.0%}**")

        st.markdown("### Kết quả chuẩn hoá")
        col_a, col_b = st.columns(2)

        with col_a:
            policy_id = st.text_input("ID (tự động)", value=ep.get("doc_id", ""), key="pol_id")

            # Category
            category_opts = [
                "return_refund",
                "shipping",
                "payment",
                "warranty",
                "promotions",
                "support",
                "account",
                "general",
            ]
            cat_val = ep.get("category") or "support"
            if cat_val not in category_opts:
                category_opts.insert(0, cat_val)
            category = st.selectbox(
                "📂 Chuyên mục (category)",
                options=category_opts,
                index=category_opts.index(cat_val),
                key="pol_category",
            )

            # Version
            version = st.text_input(
                "🔢 Phiên bản (version)",
                value=str(ep.get("version", "1.0")),
                key="pol_version",
            )

            title = st.text_input("Tiêu đề", value=ep.get("title", ""), key="pol_title")
            description = st.text_area(
                "Mô tả / Nội dung", value=ep.get("content", ""), height=140, key="pol_desc"
            )

            # Only permanent / temporary — superseded is NOT a creation option
            ptype_options = ["permanent", "temporary"]
            ptype_val = ep.get("policy_type", "permanent")
            if ptype_val not in ptype_options:
                ptype_val = "permanent"
            policy_type = st.selectbox(
                "Loại chính sách mới",
                options=ptype_options,
                index=ptype_options.index(ptype_val),
                help=(
                    "**permanent** – có hiệu lực từ ngày bắt đầu, không giới hạn thời gian.\n"
                    "**temporary** – chỉ có hiệu lực trong khoảng ngày bắt đầu → kết thúc."
                ),
                key="pol_type",
            )

            st.markdown("---")
            # Supersedes checkbox
            does_supersede = st.checkbox(
                "🔄 Chính sách này thay thế một chính sách cũ",
                key="pol_does_supersede",
                help=(
                    "Nếu tick, chính sách cũ được chọn sẽ bị đổi sang loại **superseded** "
                    "(không còn hoạt động) khi bạn lưu chính sách mới."
                ),
            )
            old_policy_id = None
            if does_supersede:
                existing = st.session_state.get("kb_policies", [])
                existing_opts = [
                    f"{p.get('doc_id', '')} — {p.get('title', '')[:50]}"
                    for p in existing
                    if p.get("policy_type") != "superseded"
                ]
                if existing_opts:
                    sel = st.selectbox(
                        "📌 Chọn chính sách bị thay thế",
                        options=["— chọn chính sách —"] + existing_opts,
                        key="pol_old_sel",
                    )
                    if sel != "— chọn chính sách —":
                        old_policy_id = sel.split(" — ")[0].strip()
                        st.warning(
                            f"⚠️ Sau khi lưu, **{old_policy_id}** sẽ bị gán `superseded = True` "
                            "và **ngừng hoạt động**."
                        )
                else:
                    old_policy_id = st.text_input(
                        "📌 ID chính sách bị thay thế (nhập thủ công)",
                        key="pol_old_manual",
                    ) or None
                    st.caption("Tải KB ở Section A trước để chọn từ danh sách.")

        with col_b:
            def _parse_ui_date(s):
                if not s:
                    return None
                try:
                    return datetime.date.fromisoformat(s)
                except Exception:
                    return None

            tags_str = st.text_input(
                "Tags (phân cách bằng dấu phẩy)",
                value=", ".join(ep.get("tags") or []),
                key="pol_tags",
            )

            eff_default = _parse_ui_date(ep.get("effective_date")) or datetime.date.today()
            start_date = st.date_input(
                "📅 Ngày có hiệu lực (effective_date)",
                value=eff_default,
                key="start_date",
            )

            end_date = None
            if policy_type == "temporary":
                exp_default = _parse_ui_date(ep.get("expiration_date")) or datetime.date.today()
                end_date = st.date_input(
                    "📅 Ngày kết thúc (expiration_date)",
                    value=exp_default,
                    key="end_date",
                )
            else:
                st.caption("ℹ️ Chính sách **permanent** không có ngày kết thúc.")

        # Save
        if st.button("💾 Lưu chính sách vào hệ thống"):
            tags_list = [t.strip() for t in tags_str.split(",") if t.strip()]
            # Compute active status and dates based on policy type
            today = datetime.date.today()
            if policy_type == "temporary":
                is_active_now = (
                    start_date is not None
                    and end_date is not None
                    and start_date <= today <= end_date
                )
                effective_date = start_date.isoformat() if start_date else None
                expiration_date = end_date.isoformat() if end_date else None
            else:
                # Permanent policies are always active and have no expiration date
                is_active_now = True
                effective_date = start_date.isoformat() if start_date else None
                expiration_date = None
            policy_obj = {
                "doc_id": policy_id.strip(),
                "category": category.strip() if category else "support",
                "title": title.strip(),
                "content": description.strip(),
                "version": version.strip() if version else "1.0",
                "is_active": is_active_now,
                "policy_type": policy_type,
                "effective_date": effective_date,
                "expiration_date": expiration_date,
                "tags": tags_list,
                "score": None,
            }
            current_staff = st.session_state.get("staff_name", "NV_CSKH_01")
            save_payload = {
                "policy": policy_obj,
                "admin_note": f"Tạo bởi {current_staff}",
                "performed_by": current_staff,
                "reason": f"Thêm mới chính sách '{policy_id.strip()}'",
            }
            try:
                save_res = requests.post(
                    f"{GATEWAY_URL}/api/v1/copilot/policy/create",
                    json=save_payload,
                    timeout=25,
                )
                if save_res.status_code in (200, 201):
                    # Flip old policy to superseded if requested
                    if does_supersede and old_policy_id:
                        try:
                            upd_payload = {
                                "updates": {"policy_type": "superseded", "is_active": False},
                                "performed_by": current_staff,
                                "reason": f"Bị thay thế bởi chính sách mới {policy_id.strip()}",
                            }
                            upd_res = requests.patch(
                                f"{GATEWAY_URL}/api/v1/copilot/policies/{old_policy_id}",
                                json=upd_payload,
                                timeout=20,
                            )
                            if upd_res.status_code == 200:
                                st.success(
                                    f"✅ Chính sách mới đã lưu. "
                                    f"Chính sách cũ **{old_policy_id}** đã được gán `superseded` (Audit Log đã ghi vết)."
                                )
                            else:
                                st.warning(
                                    f"✅ Chính sách mới đã lưu nhưng không thể cập nhật "
                                    f"chính sách cũ {old_policy_id}: {upd_res.text}"
                                )
                        except requests.RequestException as exc:
                            st.warning(f"✅ Lưu thành công nhưng không thể cập nhật chính sách cũ: {exc}")
                    else:
                        st.success("✅ Đã lưu chính sách thành công! KB đã được cập nhật và re-index.")

                    # Clear cache so Section A and Section C show fresh data
                    st.session_state.pop("policy_parsed", None)
                    st.session_state.pop("kb_policies", None)
                    st.session_state.pop("audit_logs_cache", None)
                    st.rerun()
                else:
                    st.error(f"Lưu thất bại ({save_res.status_code}): {save_res.text}")
            except requests.RequestException as exc:
                st.error(f"Không thể lưu: {exc}")

    st.markdown("---")
    # ----------------------------------------------------------------
    # SECTION C: Lịch sử phiên bản & Khôi phục (Audit Log & Rollback)
    # ----------------------------------------------------------------
    with st.expander("📜 Lịch sử phiên bản & Khôi phục (Audit Log & Rollback)", expanded=True):
        st.caption(
            "Ghi lại toàn bộ snapshot trước và sau mỗi lần tạo mới, sửa đổi hoặc thay thế chính sách. "
            "Nhân viên có thể kiểm tra ai đã sửa và **khôi phục (Rollback / Undo)** về phiên bản trước."
        )

        col_audit_btn, col_audit_stat = st.columns([1, 3])
        with col_audit_btn:
            fetch_logs = st.button("🔄 Tải / Làm mới Lịch sử")

        if fetch_logs or "audit_logs_cache" not in st.session_state:
            try:
                log_res = requests.get(
                    f"{GATEWAY_URL}/api/v1/copilot/policies/audit-logs",
                    timeout=15,
                )
                if log_res.status_code == 200:
                    st.session_state["audit_logs_cache"] = log_res.json()
                else:
                    st.error(f"Không thể tải Audit Log: {log_res.text}")
            except requests.RequestException as exc:
                st.error(f"Lỗi kết nối Audit Log: {exc}")

        audit_logs = st.session_state.get("audit_logs_cache", [])

        if audit_logs:
            # Metrics
            total_logs = len(audit_logs)
            create_cnt = sum(1 for x in audit_logs if x.get("action") == "CREATE")
            supersede_cnt = sum(1 for x in audit_logs if x.get("action") == "SUPERSEDE")
            rollback_cnt = sum(1 for x in audit_logs if x.get("action") == "ROLLBACK")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Tổng số thay đổi", total_logs)
            m2.metric("🟢 Thêm mới (CREATE)", create_cnt)
            m3.metric("🔴 Thay thế (SUPERSEDE)", supersede_cnt)
            m4.metric("🟣 Hoàn tác (ROLLBACK)", rollback_cnt)

            # Table display
            log_table = []
            action_badge_map = {
                "CREATE": "🟢 CREATE",
                "UPDATE": "🟡 UPDATE",
                "SUPERSEDE": "🔴 SUPERSEDE",
                "ROLLBACK": "🟣 ROLLBACK",
            }
            for entry in audit_logs:
                ts = entry.get("timestamp", "")
                ts_display = ts[:19].replace("T", " ") if ts else "—"
                act = entry.get("action", "")
                badge = action_badge_map.get(act, act)
                log_table.append({
                    "Log ID": entry.get("log_id", ""),
                    "Thời gian": ts_display,
                    "Mã chính sách": entry.get("doc_id", ""),
                    "Hành động": badge,
                    "Người thực hiện": entry.get("performed_by", "Admin"),
                    "Lý do / Ghi chú": entry.get("reason", "") or "—",
                })

            df_logs = pd.DataFrame(log_table)
            st.dataframe(df_logs, use_container_width=True, height=280)

            # Detailed Inspection & Rollback Interface
            st.markdown("#### 🔍 Chi tiết bản ghi & Khôi phục (Rollback)")
            log_options = [
                f"{e.get('log_id')} | {e.get('action')} | {e.get('doc_id')} ({e.get('timestamp', '')[:19]})"
                for e in audit_logs
            ]
            selected_option = st.selectbox(
                "Chọn bản ghi Audit Log để kiểm tra hoặc hoàn tác:",
                options=log_options,
                key="audit_log_selected_option",
            )

            if selected_option:
                sel_log_id = selected_option.split(" | ")[0].strip()
                matched_entry = next((e for e in audit_logs if e.get("log_id") == sel_log_id), None)

                if matched_entry:
                    col_b_info, col_a_info = st.columns(2)
                    with col_b_info:
                        st.markdown("**Trạng thái TRƯỚC khi thay đổi (Before Snapshot):**")
                        b_snap = matched_entry.get("before_snapshot")
                        if b_snap:
                            st.json(b_snap)
                        else:
                            st.info("*(Không có - Chính sách chưa tồn tại trước đó)*")

                    with col_a_info:
                        st.markdown("**Trạng thái SAU khi thay đổi (After Snapshot):**")
                        a_snap = matched_entry.get("after_snapshot")
                        if a_snap:
                            st.json(a_snap)
                        else:
                            st.info("*(Không có - Chính sách đã bị gỡ bỏ)*")

                    st.markdown("---")
                    col_rb_reason, col_rb_action = st.columns([2, 1])
                    with col_rb_reason:
                        rb_reason_input = st.text_input(
                            "Lý do khôi phục (Audit note)",
                            value=f"Nhân viên {st.session_state.get('staff_name', 'NV_CSKH_01')} khôi phục thao tác {matched_entry.get('action')}",
                            key="rb_reason_text",
                        )
                    with col_rb_action:
                        st.write("")  # padding
                        st.write("")
                        btn_label = f"⏪ Hoàn tác {matched_entry.get('action')} (Rollback)"
                        if st.button(btn_label, type="primary", key="btn_do_rollback"):
                            with st.spinner("Đang khôi phục chính sách và re-index Knowledge Base..."):
                                try:
                                    rb_payload = {
                                        "log_id": sel_log_id,
                                        "performed_by": st.session_state.get("staff_name", "NV_CSKH_01"),
                                        "reason": rb_reason_input.strip(),
                                    }
                                    rb_res = requests.post(
                                        f"{GATEWAY_URL}/api/v1/copilot/policies/rollback",
                                        json=rb_payload,
                                        timeout=25,
                                    )
                                    if rb_res.status_code == 200:
                                        res_data = rb_res.json()
                                        st.success(f"🎉 {res_data.get('message', 'Khôi phục thành công!')}")
                                        # Clear all relevant session caches
                                        st.session_state.pop("kb_policies", None)
                                        st.session_state.pop("audit_logs_cache", None)
                                        st.rerun()
                                    else:
                                        st.error(f"Khôi phục thất bại ({rb_res.status_code}): {rb_res.text}")
                                except requests.RequestException as exc:
                                    st.error(f"Lỗi khi gửi yêu cầu khôi phục: {exc}")
        else:
            st.info("Chưa có bản ghi Audit Log nào. Mọi thao tác thêm/sửa chính sách sẽ tự động được lưu lại tại đây.")



