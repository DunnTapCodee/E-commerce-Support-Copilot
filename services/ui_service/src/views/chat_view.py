"""Chat View: Multi-turn Customer Conversation, Copilot Draft Engine & Dynamic Order Assistant."""
import time
import requests
import streamlit as st


def render_chat_view(gateway_url: str):
    st.markdown("### 💬 Hỗ trợ CSKH & Đồng hành Copilot AI (Module 1, 2, 3)")
    st.caption("Hệ thống hội thoại đa lượt, tự động tra cứu đơn hàng động và đề xuất câu trả lời chuẩn chính sách.")

    # Session State Initialization for Chat
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "session_id" not in st.session_state:
        import uuid
        st.session_state.session_id = f"sess_{uuid.uuid4().hex[:8]}"
    if "current_response" not in st.session_state:
        st.session_state.current_response = None
    if "is_live_chat" not in st.session_state:
        st.session_state.is_live_chat = False

    # Top Control Bar
    col_session, col_handover, col_clear = st.columns([3, 2, 1])
    with col_session:
        st.text(f"Session ID: {st.session_state.session_id}")
    with col_handover:
        handover_text = "🟢 Đang ở chế độ Nhân viên (Live Chat)" if st.session_state.is_live_chat else "🤖 Đang ở chế độ Copilot AI"
        if st.button(f"Chuyển đổi: {handover_text}", key="btn_toggle_handover"):
            st.session_state.is_live_chat = not st.session_state.is_live_chat
            st.rerun()
    with col_clear:
        if st.button("🗑️ Xóa đoạn chat", key="btn_clear_chat"):
            st.session_state.messages = []
            st.session_state.current_response = None
            st.rerun()

    # Chat History Container
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.messages:
            role = msg.get("role", "customer")
            content = msg.get("content", "")
            if role == "customer":
                with st.chat_message("user", avatar="👤"):
                    st.write(content)
            elif role == "agent":
                if msg.get("is_acknowledgement"):
                    with st.chat_message("assistant", avatar="⚡"):
                        st.caption("⚡ *Phản hồi đệm tức thì từ Copilot:*")
                        st.write(content)
                else:
                    with st.chat_message("assistant", avatar="🎧"):
                        st.caption("👤 *Nhân viên CSKH (Đã duyệt):*")
                        st.write(content)
                        if msg.get("citations"):
                            cits = ", ".join([f"**[{c.get('doc_id')}]** {c.get('title')}" for c in msg.get("citations")])
                            st.caption(f"📚 Căn cứ chính sách: {cits}")

    # Input Box
    customer_query = st.chat_input("Nhập tin nhắn của khách hàng (ví dụ: 'Kiểm tra đơn ORD-2024-001 giúp mình')...")

    if customer_query:
        # Append customer message
        st.session_state.messages.append({"role": "customer", "content": customer_query})

        has_error = False
        with st.spinner("Copilot đang phân tích ý định, kiểm tra an toàn và tra cứu dữ liệu..."):
            try:
                payload = {
                    "query": customer_query,
                    "session_id": st.session_state.session_id,
                }
                resp = requests.post(f"{gateway_url}/api/v1/copilot/query", json=payload, timeout=25.0)
                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state.current_response = data

                    # Deliver ONLY the instant buffer acknowledgement to conversation
                    # The official draft is placed in the CS Agent panel for human review & approval
                    ack = data.get("customer_acknowledgement")
                    if ack and ack.strip():
                        st.session_state.messages.append({
                            "role": "agent",
                            "content": ack,
                            "is_acknowledgement": True,
                        })
                else:
                    has_error = True
                    st.error(f"⚠️ Lỗi từ API Gateway ({resp.status_code}): {resp.text}")
            except Exception as e:
                has_error = True
                st.error(
                    f"⚠️ Không thể kết nối API Gateway tại `{gateway_url}`: {str(e)}.\n\n"
                    "💡 **Hướng dẫn:** Vui lòng đảm bảo các microservices đã được khởi động bằng lệnh:\n"
                    "```powershell\npython run_dev.py\n```"
                )

        if not has_error:
            st.rerun()

    # Copilot Guidance & Draft Panel for CS Agent
    curr = st.session_state.current_response
    if curr:
        st.divider()
        st.markdown("#### 🛡️ Khung phân tích & Bản nháp Copilot dành cho Nhân viên CSKH")

        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.markdown("##### 🔍 Thông tin phân tích hệ thống")
            intent_data = curr.get("intent", {})
            intent_name = intent_data.get("intent", "N/A")
            intent_conf = intent_data.get("confidence", 0.0)

            st.write(f"• **Ý định phân loại:** `{intent_name}` (Tin cậy: **{intent_conf:.1%}**)")
            if curr.get("input_type"):
                st.write(f"• **Loại hội thoại:** `{curr.get('input_type')}`")

            # Guardrail status
            guard = curr.get("guardrail", {})
            action_type = guard.get("action_type", "N/A")
            guard_reason = guard.get("reason", "")
            if action_type == "PROCEED_TO_LLM":
                st.success(f"✅ An toàn: {guard_reason}")
            elif action_type == "DIRECT_REFUND_FORM":
                st.warning(f"⚠️ Chặn hành động tài chính: {guard_reason}")
            else:
                st.error(f"🛑 Chặn an toàn (Cần nhân viên): {guard_reason}")

            # Dynamic Order Card if available
            order_data = curr.get("order_data")
            if order_data:
                st.markdown("##### 📦 Thông tin đơn hàng tra cứu được")
                with st.expander(f"Đơn hàng #{order_data.get('order_id')} - {order_data.get('status')}", expanded=True):
                    st.write(f"• **Khách hàng:** {order_data.get('customer_name')} ({order_data.get('phone')})")
                    st.write(f"• **Sản phẩm:** {', '.join([it.get('name', '') for it in order_data.get('items', [])])}")
                    st.write(f"• **Tổng tiền:** {order_data.get('total_amount', 0):,} VND ({order_data.get('payment_method')})")
                    st.write(f"• **Dự kiến giao:** {order_data.get('estimated_delivery')}")
                    if order_data.get("carrier"):
                        st.write(f"• **Vận chuyển:** {order_data.get('carrier')} (Mã tracking: `{order_data.get('tracking_code')}`)")

            # Citations
            citations = curr.get("citations", [])
            if citations:
                st.markdown("##### 📖 Căn cứ chính sách trích xuất")
                for c in citations:
                    st.info(f"**[{c.get('doc_id')}] {c.get('title')}**\n\n{c.get('content')[:180]}...")

        with col_right:
            st.markdown("##### ✍️ Bản nháp phản hồi đề xuất")

            # Part 1: Buffer Acknowledgement
            ack_text = curr.get("customer_acknowledgement")
            if ack_text:
                st.markdown(f"**[Phần 1 - Đệm tức thì gửi khách]:**\n> *\"{ack_text}\"*")

            # Part 2: Main Draft
            draft_text = curr.get("draft_text", "")
            edited_draft = st.text_area("Chỉnh sửa nội dung trước khi gửi:", value=draft_text, height=180)

            col_btn1, col_btn2, col_btn3 = st.columns(3)
            with col_btn1:
                if st.button("🚀 Phê duyệt & Gửi", key="btn_approve_send", type="primary"):
                    # Append approved agent response to chat
                    st.session_state.messages.append({
                        "role": "agent",
                        "content": edited_draft,
                        "citations": curr.get("citations", []),
                        "is_acknowledgement": False,
                    })
                    # Send telemetry feedback
                    try:
                        requests.post(
                            f"{gateway_url}/api/v1/copilot/action",
                            json={
                                "interaction_id": curr.get("interaction_id", ""),
                                "action": "EDIT" if edited_draft != draft_text else "APPROVE",
                                "final_text": edited_draft,
                                "agent_notes": "Sent via Streamlit UI after CS review",
                                "handling_time_ms": 1500,
                            },
                            timeout=5.0,
                        )
                    except Exception:
                        pass
                    st.session_state.current_response = None
                    st.rerun()

            with col_btn2:
                if st.button("🔄 Tạo lại bản nháp", key="btn_regenerate"):
                    st.info("Yêu cầu sinh lại bản nháp...")

            with col_btn3:
                if st.button("❌ Từ chối bản nháp", key="btn_reject_draft"):
                    st.session_state.current_response = None
                    st.rerun()

