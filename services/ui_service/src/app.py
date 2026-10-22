
"""Streamlit CSKH Agent Workbench and Telemetry Dashboard on Port 8501."""
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

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

tab1, tab2 = st.tabs(
    ["💬 Agent Workbench", "📊 Audit & Analytics Dashboard"]
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
            st.subheader("🔍 Thông tin kiểm tra & Safety Guardrail")

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
            st.subheader("📝 Bản nháp Copilot (Nhân viên kiểm duyệt)")

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
                    f"Interaction này đã ghi nhận quyết định: "
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
