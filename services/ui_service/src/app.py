"""Streamlit CSKH Agent Workbench and Telemetry Dashboard on Port 8501."""
import os
import sys
import time
import uuid
from pathlib import Path
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
st.caption("Distributed Microservices Architecture · Module 3 Dynamic Orders & Tool Calling Active")

# Initialize session state
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "current_response" not in st.session_state:
    st.session_state.current_response = None
if "request_started" not in st.session_state:
    st.session_state.request_started = None

tab1, tab2 = st.tabs(["💬 Agent Workbench", "📊 Audit & Analytics Dashboard"])

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
                placeholder="Ví dụ: Kiểm tra trạng thái đơn ORD-1001, hoặc Hủy đơn ORD-1026 giúp tôi...",
                height=140,
            )
            customer_account = st.text_input("Mã định danh khách hàng (Customer ID)", value="demo-customer")
            submit_btn = st.form_submit_button("⚡ Phân tích & Tạo nháp", type="primary", use_container_width=True)

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
                    with st.spinner("Gateway đang điều phối phân tích & gọi tool..."):
                        res = requests.post(
                            f"{GATEWAY_URL}/api/v1/copilot/query",
                            json=payload,
                            timeout=35,
                        )
                    if res.status_code == 200:
                        st.session_state.current_response = res.json()
                    else:
                        st.error(f"Gateway trả về lỗi ({res.status_code}): {res.text}")
                except Exception as e:
                    st.error(f"Không thể kết nối đến Gateway ({GATEWAY_URL}): {e}")

        # Inspection Section
        resp = st.session_state.current_response
        if resp:
            st.markdown("---")
            st.subheader("🔍 Thông tin kiểm tra & Safety Guardrail")
            intent_info = resp.get("intent", {})
            guard_info = resp.get("guardrail", {})

            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Ý định dự đoán", intent_info.get("intent", "N/A"))
            with c2:
                conf = intent_info.get("confidence", 0.0)
                st.metric("Confidence", f"{conf:.1%}")
            with c3:
                guard_act = guard_info.get("action_type", "UNKNOWN")
                st.metric("Trạng thái Guardrail", guard_act)

            st.write(f"**Lý do quyết định:** {guard_info.get('reason', '')}")
            st.write(f"**Cho phép gọi LLM:** {'✅ Có' if guard_info.get('allow_llm') else '🚫 Không'}")

            # Module 3: Tool Calling Invocations
            tool_calls = resp.get("tool_calls", [])
            if tool_calls:
                st.subheader("🛠️ Thao tác Tool Calling thời gian thực (Module 3)")
                for tc in tool_calls:
                    t_name = tc.get("tool_name")
                    t_args = tc.get("arguments", {})
                    t_lat = tc.get("latency_ms", 0.0)
                    t_res = tc.get("result", {})
                    with st.expander(f"⚙️ Tool: `{t_name}` (Độ trễ: {t_lat} ms)", expanded=True):
                        st.write(f"**Tham số truyền vào:** `{t_args}`")
                        st.json(t_res)

            # Top candidate intents
            probs = intent_info.get("all_probabilities", {})
            if probs:
                with st.expander("Phân phối xác suất Intent (Top 5)"):
                    sorted_p = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:5]
                    prob_df = pd.DataFrame(sorted_p, columns=["Intent", "Probability"])
                    st.dataframe(prob_df, use_container_width=True)

            # Citations
            citations = resp.get("citations", [])
            st.subheader("📚 Tài liệu chính sách trích dẫn")
            if citations:
                for doc in citations:
                    status_badge = "🟢 Hiệu lực" if doc.get("is_active") else "🔴 HẾT HIỆU LỰC"
                    st.markdown(f"- **[{doc.get('doc_id')}] {doc.get('title')}** (v{doc.get('version')}) · {status_badge}")
                    with st.expander(f"Xem nội dung trích lục: {doc.get('doc_id')}"):
                        st.write(doc.get("content"))
            else:
                st.info("Không có tài liệu trích dẫn nào được sử dụng.")

    with right_col:
        st.subheader("📝 Bản nháp Copilot (Nhân viên kiểm duyệt)")
        if not resp:
            st.info("Nhập câu hỏi và nhấn 'Phân tích & Tạo nháp' để bắt đầu.")
        else:
            interaction_id = resp.get("interaction_id")
            draft_text = resp.get("draft_text", "")
            order_data = resp.get("order_data")

            if order_data:
                if "orders" in order_data and isinstance(order_data["orders"], list) and len(order_data["orders"]) > 1:
                    total_cnt = len(order_data["orders"])
                    c_name = order_data.get("customer_name") or "Khách hàng"
                    st.warning(f"📦 Tìm thấy {total_cnt} đơn hàng thuộc về {c_name} (SĐT: {order_data.get('phone', 'N/A')}):")
                    for sub_ord in order_data["orders"]:
                        with st.expander(f"🛒 Đơn hàng: `{sub_ord.get('order_id')}` - Trạng thái: {sub_ord.get('order_status')} ({sub_ord.get('total_amount', 0):,}đ)", expanded=True):
                            st.json(sub_ord)
                else:
                    st.warning("📦 Dữ liệu đơn hàng thời gian thực (SQLite Indexed + LRU Cache):")
                    st.json(order_data)

            edited_text = st.text_area(
                "Xem lại và chỉnh sửa nội dung trước khi gửi cho khách hàng:",
                value=draft_text,
                height=260,
                key=f"edit_box_{interaction_id}",
            )
            agent_notes = st.text_input("Ghi chú của nhân viên CSKH (không bắt buộc):", key=f"notes_{interaction_id}")

            st.caption("🔒 Thao tác ghi nhận vào Telemetry Audit Log; hệ thống tuân thủ Human-in-the-Loop.")

            col_a, col_b = st.columns(2)
            col_c, col_d = st.columns(2)

            def submit_human_action(action_type: str, text_payload: str):
                handling_time = int(
                    (time.perf_counter() - st.session_state.request_started) * 1000
                ) if st.session_state.request_started else 0

                payload = {
                    "interaction_id": interaction_id,
                    "action": action_type,
                    "final_text": text_payload,
                    "agent_notes": agent_notes or None,
                    "handling_time_ms": handling_time,
                }
                try:
                    res = requests.post(f"{GATEWAY_URL}/api/v1/copilot/action", json=payload, timeout=5)
                    if res.status_code == 200:
                        st.success(f"Đã lưu audit log hành động: **{action_type}** ({handling_time} ms)")
                    else:
                        st.error(f"Lỗi ghi log: {res.text}")
                except Exception as ex:
                    st.error(f"Không thể gửi audit action: {ex}")

            if col_a.button("✅ Duyệt & Gửi (Approve)", type="primary", use_container_width=True):
                submit_human_action("APPROVE", edited_text)

            if col_b.button("✏️ Chỉnh sửa & Gửi (Edit)", use_container_width=True):
                submit_human_action("EDIT", edited_text)

            if col_c.button("❌ Từ chối nháp (Reject)", use_container_width=True):
                submit_human_action("REJECT", None)

            if col_d.button("🚨 Chuyển cấp trên (Escalate)", use_container_width=True):
                submit_human_action("ESCALATE", None)

# ====================================================================
# TAB 2: Audit & Analytics Dashboard
# ====================================================================
with tab2:
    st.subheader("📈 Telemetry & Operational Analytics")
    if st.button("🔄 Làm mới dữ liệu", type="secondary"):
        st.rerun()

    try:
        stats_res = requests.get(f"{GATEWAY_URL}/api/v1/copilot/stats", timeout=5)
        if stats_res.status_code == 200:
            stats = stats_res.json()
            total_logs = stats.get("total_interactions", 0)
            avg_lat = stats.get("average_latency_ms", 0.0)
            actions_breakdown = stats.get("actions_breakdown", {})
            recent_logs = stats.get("recent_records", [])
            cache_info = stats.get("cache_stats", {})

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Tổng tương tác", total_logs)
            m2.metric("Thời gian xử lý TB", f"{avg_lat:.1f} ms")
            m3.metric("Số lượt đã duyệt/sửa", sum(actions_breakdown.values()))
            approval_rate = (
                (actions_breakdown.get("APPROVE", 0) / max(1, sum(actions_breakdown.values()))) * 100
            )
            m4.metric("Tỷ lệ chấp thuận", f"{approval_rate:.1f}%")

            # Module 3 Cache Metrics
            if cache_info:
                st.markdown("---")
                st.subheader("⚡ Hiệu năng Bộ nhớ đệm (Order LRU Cache - Module 3)")
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Cache Hit Ratio", f"{cache_info.get('hit_ratio_percent', 0.0):.1f}%")
                k2.metric("Cache Hits", cache_info.get("hits", 0))
                k3.metric("Cache Misses", cache_info.get("misses", 0))
                k4.metric("Quy mô Cache hiện tại", f"{cache_info.get('size', 0)} / {cache_info.get('max_size', 256)}")

            st.markdown("---")
            c_chart, c_table = st.columns([1, 2])
            with c_chart:
                st.subheader("Phân bổ hành động nhân viên")
                if actions_breakdown:
                    df_actions = pd.DataFrame(
                        list(actions_breakdown.items()), columns=["Hành động", "Số lượng"]
                    )
                    st.bar_chart(df_actions.set_index("Hành động"))
                else:
                    st.info("Chưa có hành động kiểm duyệt nào được ghi lại.")

            with c_table:
                st.subheader("Nhật ký tương tác gần nhất")
                if recent_logs:
                    log_df = pd.DataFrame(recent_logs)[
                        ["interaction_id", "timestamp", "customer_query", "predicted_intent", "guardrail_action", "human_action", "latency_ms"]
                    ]
                    st.dataframe(log_df, use_container_width=True, height=350)
                else:
                    st.info("Chưa có bản ghi tương tác nào trong cơ sở dữ liệu.")
        else:
            st.error(f"Không thể lấy thống kê từ Gateway: {stats_res.text}")
    except Exception as ex:
        st.warning(f"Chưa kết nối được với Telemetry Service qua Gateway: {ex}")
