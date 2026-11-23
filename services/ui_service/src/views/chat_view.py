"""Chat View: Multi-turn Customer Conversation, Copilot Draft Engine & Dynamic Order Assistant."""
import time
import uuid
import requests
import streamlit as st

MOCK_CUSTOMERS = [
    {
        "id": "CUST-1100",
        "name": "Lê Văn Sơn",
        "phone": "0998.708.581",
        "order_id": "ORD-1100",
        "status": "Delivered",
        "summary": "1.950.000 VNĐ - Chuột Logitech MX Master 3S",
    },
    {
        "id": "CUST-1002",
        "name": "Phan Văn An",
        "phone": "0974.716.127",
        "order_id": "ORD-1002",
        "status": "Shipping",
        "summary": "912.000 VNĐ - Giày thể thao Biti's Hunter",
    },
    {
        "id": "CUST-1001",
        "name": "Bùi Thị An",
        "phone": "0938.242.854",
        "order_id": "ORD-1001",
        "status": "Shipping",
        "summary": "1.402.000 VNĐ - Bộ drap ga giường cotton",
    },
    {
        "id": "CUST-GUEST",
        "name": "Khách vãng lai (Chưa đăng nhập)",
        "phone": "Chưa cung cấp",
        "order_id": None,
        "status": None,
        "summary": "Chưa có thông tin đơn hàng",
    },
]


def render_chat_view(gateway_url: str):
    st.markdown("### 💬 Hỗ trợ CSKH & Đồng hành Copilot AI (Đa khách hàng & Đa phiên)")

    # 1. State Management for Customers & Sessions
    if "selected_customer_id" not in st.session_state:
        st.session_state.selected_customer_id = "CUST-1100"

    if "customer_sessions" not in st.session_state:
        init_sess_id = f"sess_{uuid.uuid4().hex[:8]}"
        st.session_state.customer_sessions = {
            "CUST-1100": [
                {
                    "session_id": init_sess_id,
                    "title": "Tra cứu đơn ORD-1100",
                    "messages": [],
                    "current_response": None,
                    "created_at": time.strftime("%H:%M"),
                }
            ]
        }

    cust_map = {c["id"]: c for c in MOCK_CUSTOMERS}
    curr_cust_id = st.session_state.selected_customer_id
    curr_cust = cust_map.get(curr_cust_id, MOCK_CUSTOMERS[0])

    if curr_cust_id not in st.session_state.customer_sessions:
        new_id = f"sess_{uuid.uuid4().hex[:8]}"
        st.session_state.customer_sessions[curr_cust_id] = [
            {
                "session_id": new_id,
                "title": "Hội thoại mới",
                "messages": [],
                "current_response": None,
                "created_at": time.strftime("%H:%M"),
            }
        ]

    sessions_list = st.session_state.customer_sessions[curr_cust_id]
    if "active_session_id" not in st.session_state or not any(s["session_id"] == st.session_state.active_session_id for s in sessions_list):
        st.session_state.active_session_id = sessions_list[0]["session_id"]

    active_session = next(s for s in sessions_list if s["session_id"] == st.session_state.active_session_id)

    # 2. Layout: 3 Columns
    col_sessions, col_chat, col_copilot = st.columns([1.1, 2.3, 1.8], gap="medium")

    # -----------------------------------------------------------------
    # COLUMN 1: Customer Selector & Session List
    # -----------------------------------------------------------------
    with col_sessions:
        st.markdown("##### 👥 Khách Hàng")
        cust_options = [c["id"] for c in MOCK_CUSTOMERS]
        cust_labels = {c["id"]: f"{c['name']} ({c['id']})" for c in MOCK_CUSTOMERS}

        selected_id = st.selectbox(
            "Chọn hồ sơ khách hàng:",
            options=cust_options,
            format_func=lambda cid: cust_labels.get(cid, cid),
            index=cust_options.index(curr_cust_id) if curr_cust_id in cust_options else 0,
            key="customer_dropdown_select",
        )

        if selected_id != curr_cust_id:
            st.session_state.selected_customer_id = selected_id
            st.session_state.active_session_id = None
            st.rerun()

        # Mini Customer Card
        with st.container():
            st.info(
                f"**👤 {curr_cust['name']}**\n\n"
                f"• SĐT: `{curr_cust['phone']}`\n\n"
                f"• Đơn gần nhất: `{curr_cust.get('order_id') or 'N/A'}`\n\n"
                f"• Trạng thái: **{curr_cust.get('status') or 'Không'}**"
            )

        st.divider()

        # Sessions List
        col_s_title, col_s_add = st.columns([2, 1])
        with col_s_title:
            st.markdown(f"**Danh sách phiên** ({len(sessions_list)})")
        with col_s_add:
            if st.button("➕ Mới", key="btn_add_session", use_container_width=True):
                new_sess_id = f"sess_{uuid.uuid4().hex[:8]}"
                count = len(sessions_list) + 1
                new_sess = {
                    "session_id": new_sess_id,
                    "title": f"Hội thoại #{count}",
                    "messages": [],
                    "current_response": None,
                    "created_at": time.strftime("%H:%M"),
                }
                st.session_state.customer_sessions[curr_cust_id].insert(0, new_sess)
                st.session_state.active_session_id = new_sess_id
                st.rerun()

        for s in sessions_list:
            is_active = (s["session_id"] == active_session["session_id"])
            msg_count = len(s["messages"])
            btn_label = f"{'👉 ' if is_active else ''}{s['title']} ({msg_count} tin)"
            if st.button(btn_label, key=f"sess_btn_{s['session_id']}", use_container_width=True, type="primary" if is_active else "secondary"):
                st.session_state.active_session_id = s["session_id"]
                st.rerun()

    # -----------------------------------------------------------------
    # COLUMN 2: Customer Dialogue Stream
    # -----------------------------------------------------------------
    with col_chat:
        st.markdown(f"##### 💬 Hội thoại: {curr_cust['name']} (`{active_session['session_id']}`)")

        chat_container = st.container(height=450)
        with chat_container:
            if not active_session["messages"]:
                st.caption(f"Chưa có tin nhắn trong phiên này với khách hàng {curr_cust['name']}. Hãy nhập câu hỏi bên dưới.")
            for msg in active_session["messages"]:
                role = msg.get("role", "customer")
                content = msg.get("content", "")
                if role == "customer":
                    with st.chat_message("user", avatar="👤"):
                        st.write(content)
                elif role == "agent":
                    if msg.get("is_acknowledgement"):
                        with st.chat_message("assistant", avatar="⚡"):
                            st.caption("⚡ *Phản hồi đệm tức thì (Copilot):*")
                            st.write(content)
                    else:
                        with st.chat_message("assistant", avatar="🎧"):
                            st.caption("👤 *Nhân viên CSKH (Đã duyệt):*")
                            st.write(content)
                            if msg.get("citations"):
                                cits = ", ".join([f"**[{c.get('doc_id')}]** {c.get('title')}" for c in msg.get("citations")])
                                st.caption(f"📚 Căn cứ chính sách: {cits}")

        # Input query
        customer_query = st.chat_input(f"Nhập câu hỏi từ {curr_cust['name']} (ví dụ: 'Đơn hàng của mình là gì nhỉ')...")
        if customer_query:
            # First message auto-renames session
            if not active_session["messages"]:
                title_snip = customer_query.strip()[:24]
                active_session["title"] = title_snip if len(customer_query) <= 24 else f"{title_snip}..."

            # 1. Optimistically append Customer Query
            active_session["messages"].append({"role": "customer", "content": customer_query})

            # 2. Immediately determine Contextual Instant Buffer Acknowledgement ("CÂU CHỜ")
            initial_ack = "Dạ em đã ghi nhận thông tin của anh/chị và đang kiểm tra hỗ trợ ngay đây ạ! Quý khách đợi em trong giây lát nhé..."
            q_low = customer_query.lower()
            if any(k in q_low for k in ["hủy", "huy", "cancel"]):
                initial_ack = "Dạ em đã nhận được yêu cầu hủy đơn hàng của mình. Em đang kiểm tra trạng thái đóng gói đơn hàng để xử lý ngay đây ạ..."
            elif any(k in q_low for k in ["đổi", "doi", "trả", "tra", "hoàn", "hoan"]):
                initial_ack = "Dạ Tiki đã ghi nhận yêu cầu về chính sách đổi trả / hoàn tiền. Em đang tra cứu quy định và dữ liệu đơn hàng cho mình ngay đây ạ..."
            elif any(k in q_low for k in ["giao", "ship", "ord-", "đơn", "khi nào", "bao giờ"]):
                initial_ack = "Dạ em đã ghi nhận câu hỏi về tình trạng đơn hàng của anh/chị. Em đang kết nối tra cứu lộ trình vận chuyển ngay đây ạ!"

            ack_entry = {
                "role": "agent",
                "content": initial_ack,
                "is_acknowledgement": True,
            }
            active_session["messages"].append(ack_entry)

            with st.spinner("Copilot đang phân tích và chuẩn bị câu trả lời..."):
                try:
                    payload = {
                        "query": customer_query,
                        "session_id": active_session["session_id"],
                        "customer_id": curr_cust["id"],
                    }
                    resp = requests.post(f"{gateway_url}/api/v1/copilot/query", json=payload, timeout=20.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        active_session["current_response"] = data

                        # Update buffer acknowledgement with tailored backend message if present
                        ack = data.get("customer_acknowledgement")
                        if ack and ack.strip():
                            ack_entry["content"] = ack
                    else:
                        st.error(f"⚠️ Lỗi từ Gateway ({resp.status_code}): {resp.text}")
                except Exception as e:
                    st.error(f"⚠️ Không thể kết nối API Gateway: {str(e)}")

            st.rerun()

    # -----------------------------------------------------------------
    # COLUMN 3: Copilot CS Support & Draft Editor
    # -----------------------------------------------------------------
    with col_copilot:
        st.markdown("##### 🛡️ Khung làm việc Copilot")
        curr = active_session.get("current_response")
        if curr:
            # 1. Intent & Guardrail
            intent_data = curr.get("intent", {})
            intent_name = intent_data.get("intent", "N/A")
            intent_conf = intent_data.get("confidence", 0.0)
            guard = curr.get("guardrail", {})
            action_type = guard.get("action_type", "N/A")

            st.markdown(f"• **Ý định:** `{intent_name}` ({intent_conf:.0%})")
            if action_type == "PROCEED_TO_LLM":
                st.success(f"✅ An toàn: {guard.get('reason', '')}")
            elif action_type == "DIRECT_REFUND_FORM":
                st.warning(f"⚠️ Chặn tài chính: {guard.get('reason', '')}")
            else:
                st.error(f"🛑 Chặn: {guard.get('reason', '')}")

            # 2. Dynamic Order
            order_data = curr.get("order_data")
            if order_data:
                with st.expander(f"📦 Đơn #{order_data.get('order_id')} ({order_data.get('status')})", expanded=True):
                    st.write(f"• **Khách:** {order_data.get('customer_name')} ({order_data.get('phone')})")
                    st.write(f"• **Tiền:** {order_data.get('total_amount', 0):,} VND ({order_data.get('payment_method')})")
                    st.write(f"• **Dự kiến:** {order_data.get('estimated_delivery')}")

            # 3. Draft Editor
            ack_text = curr.get("customer_acknowledgement")
            if ack_text:
                st.caption(f"⚡ *Câu đệm đã gửi tự động:* \"{ack_text}\"")

            draft_text = curr.get("draft_text", "")
            edited_draft = st.text_area("Bản nháp đề xuất cho nhân viên duyệt:", value=draft_text, height=150, key=f"draft_{active_session['session_id']}")

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("🚀 Duyệt & Gửi", key="btn_approve_send", type="primary", use_container_width=True):
                    active_session["messages"].append({
                        "role": "agent",
                        "content": edited_draft,
                        "citations": curr.get("citations", []),
                        "is_acknowledgement": False,
                    })
                    # Feedback
                    try:
                        requests.post(
                            f"{gateway_url}/api/v1/copilot/action",
                            json={
                                "interaction_id": curr.get("interaction_id", ""),
                                "action": "EDIT" if edited_draft != draft_text else "APPROVE",
                                "final_text": edited_draft,
                                "agent_notes": f"Approved by CS for {curr_cust['name']}",
                                "handling_time_ms": 1200,
                            },
                            timeout=5.0,
                        )
                    except Exception:
                        pass
                    active_session["current_response"] = None
                    st.rerun()

            with col_btn2:
                if st.button("❌ Bỏ qua", key="btn_reject_draft", use_container_width=True):
                    active_session["current_response"] = None
                    st.rerun()

            # 4. Citations
            citations = curr.get("citations", [])
            if citations:
                with st.expander("📚 Căn cứ chính sách trích xuất", expanded=False):
                    for c in citations:
                        st.info(f"**[{c.get('doc_id')}] {c.get('title')}**\n\n{c.get('content')[:180]}...")
        else:
            st.info("ℹ️ Khi khách gửi câu hỏi, AI Copilot sẽ tự động phân tích và sinh bản nháp hoàn chỉnh tại đây để nhân viên CSKH duyệt.")
