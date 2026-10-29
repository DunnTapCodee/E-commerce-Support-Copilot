"""Streamlit CSKH Agent Workbench and Customer Chat Simulator.

Dribbble-grade SaaS layout with 2 synchronized Chat Views:
1. Customer Chat (Live Chat Simulator, human-in-the-loop)
2. Agent Copilot Workbench (Live Conversation Stream, AI Drafts, Order & Policy Inspector)
3. Audit & Telemetry Dashboard
"""

import datetime
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8000")

# -----------------------------------------------------------------------------
# Streamlit Page Setup
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="E-Commerce Support Copilot · NextGen Workbench",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# Session State Initialization
# -----------------------------------------------------------------------------
if "session_id" not in st.session_state:
    st.session_state.session_id = f"SES-{uuid.uuid4().hex[:8].upper()}"

if "customer_id" not in st.session_state:
    st.session_state.customer_id = "cust-1004"

if "theme" not in st.session_state:
    st.session_state.theme = "light"

if "is_live_chat" not in st.session_state:
    st.session_state.is_live_chat = False

if "pending_agent_review" not in st.session_state:
    st.session_state.pending_agent_review = False

if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        {
            "role": "assistant",
            "content": "Xin chào quý khách! Em là nhân viên hỗ trợ CSKH Tiki. Em có thể hỗ trợ quý khách tra cứu đơn hàng, tư vấn chính sách bảo hành, đổi trả hàng hoặc xử lý yêu cầu khiếu nại.",
            "timestamp": datetime.datetime.now().strftime("%H:%M"),
            "badge": "Chuyên viên CSKH",
        }
    ]

if "current_response" not in st.session_state:
    st.session_state.current_response = None

if "review_started_at" not in st.session_state:
    st.session_state.review_started_at = None

if "review_started_interaction_id" not in st.session_state:
    st.session_state.review_started_interaction_id = None

if "recorded_actions" not in st.session_state:
    st.session_state.recorded_actions = {}


# -----------------------------------------------------------------------------
# Dribbble-Grade Custom CSS Styling (Light / Dark Mode)
# -----------------------------------------------------------------------------
def get_custom_css(theme: str) -> str:
    """Generate dynamic CSS tailored for clean SaaS & Dribbble aesthetic."""
    if theme == "dark":
        bg_main = "#0f172a"
        bg_card = "#1e293b"
        bg_card_secondary = "#334155"
        text_primary = "#f8fafc"
        text_secondary = "#94a3b8"
        border_color = "#334155"
        accent_blue = "#38bdf8"
        accent_emerald = "#34d399"
        accent_rose = "#f43f5e"
        accent_amber = "#fbbf24"
        shadow_card = "0 8px 24px -4px rgba(0, 0, 0, 0.45)"
    else:
        bg_main = "#f8fafc"
        bg_card = "#ffffff"
        bg_card_secondary = "#f1f5f9"
        text_primary = "#0f172a"
        text_secondary = "#64748b"
        border_color = "#e2e8f0"
        accent_blue = "#0284c7"
        accent_emerald = "#059669"
        accent_rose = "#e11d48"
        accent_amber = "#d97706"
        shadow_card = "0 6px 20px -2px rgba(15, 23, 42, 0.06), 0 2px 6px -1px rgba(15, 23, 42, 0.04)"

    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {{
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }}

    .stApp {{
        background-color: {bg_main};
        color: {text_primary};
    }}

    .dribbble-card {{
        background-color: {bg_card};
        border: 1px solid {border_color};
        border-radius: 14px;
        padding: 16px 20px;
        margin-bottom: 16px;
        box-shadow: {shadow_card};
    }}

    .copilot-draft-box {{
        background-color: {bg_card_secondary};
        border: 1px dashed {accent_blue};
        border-radius: 12px;
        padding: 14px 16px;
        margin: 12px 0;
    }}

    .badge-pill {{
        display: inline-block;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.3px;
    }}

    .badge-blue {{ background-color: rgba(56, 189, 248, 0.15); color: {accent_blue}; }}
    .badge-green {{ background-color: rgba(52, 211, 153, 0.15); color: {accent_emerald}; }}
    .badge-red {{ background-color: rgba(244, 63, 94, 0.15); color: {accent_rose}; }}
    .badge-amber {{ background-color: rgba(251, 191, 36, 0.15); color: {accent_amber}; }}

    .guard-banner-red {{
        background: linear-gradient(135deg, rgba(239, 68, 68, 0.12), rgba(220, 38, 38, 0.06));
        border-left: 5px solid #ef4444;
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 12px;
    }}

    .guard-banner-yellow {{
        background: linear-gradient(135deg, rgba(245, 158, 11, 0.12), rgba(217, 119, 6, 0.06));
        border-left: 5px solid #f59e0b;
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 12px;
    }}

    .guard-banner-blue {{
        background: linear-gradient(135deg, rgba(59, 130, 246, 0.12), rgba(37, 99, 235, 0.06));
        border-left: 5px solid #3b82f6;
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 12px;
    }}

    .guard-banner-green {{
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.12), rgba(5, 150, 105, 0.06));
        border-left: 5px solid #10b981;
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 12px;
    }}

    .stButton > button {{
        border-radius: 10px;
        font-weight: 600;
        transition: all 0.2s ease;
    }}
    </style>
    """


st.markdown(get_custom_css(st.session_state.theme), unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Sidebar: Session Control & Microservice Health
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Cấu hình Hệ thống")

    theme_choice = st.radio(
        "Giao diện (Theme):",
        ["Sáng (Light Mode)", "Tối (Dark Mode)"],
        index=0 if st.session_state.theme == "light" else 1,
    )
    new_theme = "light" if "Sáng" in theme_choice else "dark"
    if new_theme != st.session_state.theme:
        st.session_state.theme = new_theme
        st.rerun()

    st.markdown("---")
    st.markdown("#### 🎫 Phiên hội thoại & Khách hàng")
    st.caption(f"Session ID: `{st.session_state.session_id}`")

    cust_options = {
        "cust-1004": "Bùi Thị An (Đơn ORD-1004)",
        "cust-1002": "Phan Văn An (Đơn ORD-1002)",
        "demo-customer": "Bùi Thị An (Đơn ORD-1001)",
        "KH-88219": "Khách hàng mới (Chưa có đơn)",
    }
    cur_idx = list(cust_options.keys()).index(st.session_state.customer_id) if st.session_state.customer_id in cust_options else 0
    selected_cust = st.selectbox(
        "Tài khoản khách hàng mô phỏng:",
        options=list(cust_options.keys()),
        format_func=lambda x: f"{x} - {cust_options.get(x, x)}",
        index=cur_idx,
    )
    if selected_cust != st.session_state.customer_id:
        st.session_state.customer_id = selected_cust
        st.rerun()

    if st.button("➕ Tạo phiên mới (New Session)", use_container_width=True):
        st.session_state.session_id = f"SES-{uuid.uuid4().hex[:8].upper()}"
        st.session_state.is_live_chat = False
        st.session_state.pending_agent_review = False
        st.session_state.current_response = None
        st.session_state.chat_history = [
            {
                "role": "assistant",
                "content": "Xin chào quý khách! Em là nhân viên hỗ trợ CSKH Tiki. Em có thể hỗ trợ gì cho quý khách?",
                "timestamp": datetime.datetime.now().strftime("%H:%M"),
                "badge": "Chuyên viên CSKH",
            }
        ]
        st.rerun()

    st.markdown("---")
    st.markdown("#### 📡 Trạng thái Dịch vụ")
    try:
        health_gw = requests.get(f"{GATEWAY_URL}/health", timeout=2)
        if health_gw.status_code == 200:
            st.success("🟢 API Gateway: Online (8000)")
        else:
            st.warning(f"🟡 Gateway: {health_gw.status_code}")
    except Exception:
        st.error("🔴 Gateway: Offline (8000)")

    st.markdown(
        """
        <div style="font-size: 12px; color: gray; margin-top: 15px;">
        <b>Microservices Topology:</b><br/>
        • Gateway: :8000<br/>
        • Conversation Service: :8001<br/>
        • RAG Service: :8002<br/>
        • Telemetry Service: :8003<br/>
        • Intent Service: :8005<br/>
        </div>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# Top Header Bar
# -----------------------------------------------------------------------------
header_col1, header_col2 = st.columns([3, 1])
with header_col1:
    st.title("⚡ E-Commerce Support Copilot")
    st.caption("Nền tảng Hỗ trợ Khách hàng Đa dịch vụ kết hợp Kiểm duyệt An toàn AI (Human-in-the-Loop)")

with header_col2:
    if st.session_state.is_live_chat:
        st.markdown(
            '<div style="text-align:right; margin-top:15px;"><span class="badge-pill badge-blue">🎧 LIVE CHAT TRỰC TIẾP</span></div>',
            unsafe_allow_html=True,
        )
    elif st.session_state.pending_agent_review:
        st.markdown(
            '<div style="text-align:right; margin-top:15px;"><span class="badge-pill badge-amber">⏳ ĐANG CHỜ CHUYÊN VIÊN DUYỆT</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="text-align:right; margin-top:15px;"><span class="badge-pill badge-green">🟢 COPILOT SẴN SÀNG</span></div>',
            unsafe_allow_html=True,
        )


# -----------------------------------------------------------------------------
# Primary Tabs: User Simulator vs. CSKH Workbench vs. Telemetry Audit
# -----------------------------------------------------------------------------
tab_user, tab_agent, tab_audit = st.tabs(
    [
        "💬 1. Trải nghiệm Khách hàng (User Chat)",
        "🛡️ 2. Bàn làm việc Chuyên viên CSKH (Agent Workbench)",
        "📊 3. Báo cáo Kiểm toán & Hiệu năng (Audit & Telemetry)",
    ]
)


# =============================================================================
# TAB 1: User Chat Simulator (Customer Interface)
# =============================================================================
with tab_user:
    st.markdown("### Khung Hội Thoại Khách Hàng")
    st.caption("Giao diện người dùng gửi thắc mắc. Câu trả lời của hệ thống PHẢI qua chuyên viên kiểm duyệt trước khi hiển thị tại đây.")

    # Render Chat History via native Streamlit chat bubbles
    with st.container(height=450):
        for msg in st.session_state.chat_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            ts = msg.get("timestamp", "")
            badge = msg.get("badge", "")

            if role == "user":
                with st.chat_message("user", avatar="👤"):
                    st.markdown(f"**Khách hàng** `{ts}`")
                    st.write(content)
            else:
                avatar = "🎧" if "Nhân viên" in badge or "Chuyên viên" in badge else "🤖"
                with st.chat_message("assistant", avatar=avatar):
                    badge_color = "#0284c7" if "Chuyên viên" in badge or "Nhân viên" in badge else "#059669"
                    st.markdown(
                        f"<span style='font-size:12px; font-weight:700; color:{badge_color};'>[{badge}]</span> "
                        f"<span style='font-size:11px; color:gray;'>· {ts}</span>",
                        unsafe_allow_html=True,
                    )
                    st.write(content)

        # Pending Indicator for customer
        if st.session_state.pending_agent_review:
            with st.chat_message("assistant", avatar="⏳"):
                st.info("💬 *Chuyên viên CSKH đang đối soát thông tin và sẽ gửi phản hồi chi tiết đến quý khách trong giây lát...*")

    # Quick Suggestion Chips
    st.markdown("<p style='font-size:13px; font-weight:600; margin-top:14px;'>⚡ Câu hỏi gợi ý nhanh:</p>", unsafe_allow_html=True)
    chip_cols = st.columns(5)
    selected_prompt = None

    if chip_cols[0].button("📦 Tra đơn ORD-1003", use_container_width=True):
        selected_prompt = "Kiểm tra tiến độ đơn hàng ORD-1003 giúp tôi"
    if chip_cols[1].button("💰 Hoàn tiền ORD-1002", use_container_width=True):
        selected_prompt = "Tôi muốn hủy và yêu cầu hoàn tiền cho đơn ORD-1002"
    if chip_cols[2].button("🔄 Đổi trả hàng lỗi", use_container_width=True):
        selected_prompt = "Chính sách đổi trả hàng bị lỗi kỹ thuật trong bao nhiêu ngày?"
    if chip_cols[3].button("🎧 Gặp chuyên viên", use_container_width=True):
        selected_prompt = "Tôi cần gặp trực tiếp nhân viên tư vấn để giải quyết khiếu nại"
    if chip_cols[4].button("🧧 Ưu đãi Tết 2023", use_container_width=True):
        selected_prompt = "Cho tôi hỏi chương trình khuyến mãi Tết 2023 còn áp dụng không?"

    # Message Input Form
    with st.form("user_chat_input_form", clear_on_submit=True):
        col_input, col_submit = st.columns([5, 1])
        with col_input:
            input_text = st.text_input(
                "Nhập tin nhắn của bạn...",
                value=selected_prompt or "",
                placeholder="Nhập câu hỏi hoặc cung cấp mã đơn hàng...",
                label_visibility="collapsed",
            )
        with col_submit:
            send_btn = st.form_submit_button("Gửi 🚀", type="primary", use_container_width=True)

    # Process User Message Submission
    if (send_btn and input_text.strip()) or selected_prompt:
        user_msg = (input_text or selected_prompt).strip()
        now_time = datetime.datetime.now().strftime("%H:%M")

        # 1. Append user message to chat history
        st.session_state.chat_history.append(
            {
                "role": "user",
                "content": user_msg,
                "timestamp": now_time,
                "badge": "Khách hàng",
            }
        )

        # 2. Dispatch to Gateway
        st.session_state.review_started_at = time.perf_counter()
        payload = {
            "query": user_msg,
            "session_id": st.session_state.session_id,
            "customer_id": st.session_state.customer_id,
        }

        try:
            with st.spinner("Copilot đang phân tích và chuẩn bị hồ sơ cho nhân viên..."):
                resp = requests.post(
                    f"{GATEWAY_URL}/api/v1/copilot/query",
                    json=payload,
                    timeout=15,
                )

            if resp.status_code == 200:
                res_data = resp.json()
                st.session_state.current_response = res_data
                st.session_state.review_started_interaction_id = res_data.get("interaction_id")

                # Check if live chat is flagged
                if res_data.get("is_live_chat"):
                    st.session_state.is_live_chat = True

                # Process response:
                customer_ack = res_data.get("customer_acknowledgement")
                input_type = res_data.get("input_type", "")
                guard_action = res_data.get("guardrail", {}).get("action_type", "")

                if input_type == "chitchat" or guard_action == "CHITCHAT_RESPONSE":
                    suggested = res_data.get("suggested_reply") or "Dạ Tiki chào bạn! Rất vui được hỗ trợ bạn hôm nay ạ."
                    st.session_state.chat_history.append(
                        {
                            "role": "assistant",
                            "content": suggested,
                            "timestamp": datetime.datetime.now().strftime("%H:%M"),
                            "badge": "Tiki AI (Chào hỏi)",
                        }
                    )
                    st.session_state.pending_agent_review = False
                else:
                    # PHẦN 1: Hiển thị ngay câu trả lời dạo trước theo ngữ cảnh cho khách
                    if customer_ack:
                        st.session_state.chat_history.append(
                            {
                                "role": "assistant",
                                "content": customer_ack,
                                "timestamp": datetime.datetime.now().strftime("%H:%M"),
                                "badge": "Tiki AI (Tiếp nhận)",
                            }
                        )
                    # Giữ cờ chờ chuyên viên duyệt ở Tab 2
                    st.session_state.pending_agent_review = True

                st.rerun()
            else:
                st.error(f"Lỗi từ Gateway ({resp.status_code}): {resp.text}")
        except Exception as exc:
            st.error(f"Không thể kết nối đến Gateway ({GATEWAY_URL}): {exc}")


# =============================================================================
# TAB 2: Agent Workbench (CSKH Workspace with Synchronized Chat & Inspector)
# =============================================================================
with tab_agent:
    st.markdown("### 🛡️ Không Gian Làm Việc Chuyên Viên CSKH (Agent Workspace)")
    st.caption("Giao diện hợp nhất: Xem luồng chat trực tiếp, nhận gợi ý từ AI Copilot, đối soát hồ sơ và duyệt gửi phản hồi.")

    current_resp = st.session_state.current_response

    # Layout: Left column = Live Conversation & Composer (58%), Right column = Copilot Inspector (42%)
    col_chat_agent, col_inspector = st.columns([12, 9], gap="large")

    # -------------------------------------------------------------------------
    # LEFT COLUMN: Live Chat Timeline + AI Draft Suggestion + Agent Composer
    # -------------------------------------------------------------------------
    with col_chat_agent:
        st.markdown("#### 💬 Luồng Trao Đổi Trực Tiếp Với Khách Hàng")

        # Live chat container (matches customer's perspective)
        with st.container(height=380):
            for msg in st.session_state.chat_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                ts = msg.get("timestamp", "")
                badge = msg.get("badge", "")

                if role == "user":
                    with st.chat_message("user", avatar="👤"):
                        st.markdown(f"**Khách hàng** `{ts}`")
                        st.write(content)
                else:
                    avatar = "🎧" if "Nhân viên" in badge or "Chuyên viên" in badge else "🤖"
                    with st.chat_message("assistant", avatar=avatar):
                        badge_color = "#0284c7" if "Chuyên viên" in badge or "Nhân viên" in badge else "#059669"
                        st.markdown(
                            f"<span style='font-size:12px; font-weight:700; color:{badge_color};'>[{badge}]</span> "
                            f"<span style='font-size:11px; color:gray;'>· {ts}</span>",
                            unsafe_allow_html=True,
                        )
                        st.write(content)

            if st.session_state.pending_agent_review:
                st.warning("⚠️ *Khách hàng đang chờ phản hồi cho tin nhắn mới nhất ở trên.*")

        # ---------------------------------------------------------------------
        # AI Draft Suggestion Box (Only if there is an active interaction)
        # ---------------------------------------------------------------------
        if current_resp:
            interaction_id = current_resp.get("interaction_id")
            draft_text = current_resp.get("draft_text", "")
            suggested_reply = current_resp.get("suggested_reply") or draft_text
            agent_guidance = current_resp.get("agent_guidance") or ""
            generation_mode = current_resp.get("generation_mode", "copilot")
            guard_info = current_resp.get("guardrail", {})
            guard_action = guard_info.get("action_type", "UNKNOWN")

            st.markdown("#### 🤖 Gợi Ý Phản Hồi Từ Copilot")

            # Notice badge on draft mode
            mode_badge = "RAG + LLM" if generation_mode == "gemini" else f"Template: {generation_mode}"
            st.caption(f"Phương thức tạo: `{mode_badge}` · Interaction ID: `{interaction_id}`")

            # Display the raw draft for review
            st.markdown(
                f"""
                <div class="copilot-draft-box">
                    <span style="font-size: 11px; font-weight: 700; color: #0284c7;">BẢN NHÁP GỢI Ý CỦA COPILOT:</span><br/>
                    <div style="font-size: 14px; margin-top: 6px; white-space: pre-wrap;">{suggested_reply}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # -----------------------------------------------------------------
            # Agent Reply Composer
            # -----------------------------------------------------------------
            st.markdown("#### ✍️ Soạn Thảo & Duyệt Gửi Cho Khách")

            if agent_guidance:
                st.info(f"💡 **Chỉ dẫn nghiệp vụ:** {agent_guidance}")

            response_editor_text = st.text_area(
                "Nội dung phản hồi chính thức (Chuyên viên có thể chỉnh sửa trước khi gửi):",
                value=suggested_reply,
                height=140,
                key=f"agent_edit_{interaction_id}",
            )

            agent_internal_notes = st.text_input(
                "Ghi chú nội bộ của chuyên viên (lưu vào audit log):",
                key=f"notes_{interaction_id}",
                placeholder="Ví dụ: Đã đối soát vận đơn GHTK, khách đồng ý nhận lại sản phẩm...",
            )

            # Action Buttons Handler
            def handle_agent_action(action_name: str, text_to_send: Optional[str]):
                """Submit action to telemetry and push reply to customer chat."""
                now = datetime.datetime.now().strftime("%H:%M")
                review_start = st.session_state.review_started_at
                handling_ms = int((time.perf_counter() - review_start) * 1000) if review_start else 0

                payload_action = {
                    "interaction_id": interaction_id,
                    "action": action_name,
                    "final_text": text_to_send,
                    "agent_notes": agent_internal_notes.strip() or None,
                    "handling_time_ms": handling_ms,
                }

                try:
                    res_act = requests.post(
                        f"{GATEWAY_URL}/api/v1/copilot/action",
                        json=payload_action,
                        timeout=5,
                    )

                    if res_act.status_code in (200, 201):
                        st.session_state.recorded_actions[interaction_id] = action_name

                        # If approved or edited, post into customer chat
                        if action_name in ("APPROVE", "EDIT") and text_to_send:
                            st.session_state.chat_history.append(
                                {
                                    "role": "assistant",
                                    "content": text_to_send,
                                    "timestamp": now,
                                    "badge": "Chuyên viên CSKH (Đã duyệt)",
                                }
                            )
                            st.session_state.pending_agent_review = False

                        st.success(f"Đã duyệt và gửi phản hồi thành công! ({handling_ms} ms)")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(f"Lỗi khi gửi action: {res_act.text}")
                except Exception as ex:
                    st.error(f"Không thể kết nối Gateway để ghi nhận action: {ex}")

            recorded_act = st.session_state.recorded_actions.get(interaction_id)

            btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)

            with btn_col1:
                if st.button(
                    "⚡ Duyệt & Gửi",
                    type="primary",
                    use_container_width=True,
                    disabled=bool(recorded_act),
                ):
                    handle_agent_action("APPROVE", response_editor_text.strip())

            with btn_col2:
                if st.button(
                    "✏️ Sửa & Gửi",
                    use_container_width=True,
                    disabled=bool(recorded_act),
                ):
                    handle_agent_action("EDIT", response_editor_text.strip())

            with btn_col3:
                is_live = st.session_state.is_live_chat
                live_label = "🔌 Thoát Live Chat" if is_live else "🎧 Nhận Live Chat"
                if st.button(live_label, use_container_width=True):
                    new_live = not is_live
                    try:
                        requests.post(
                            f"{GATEWAY_URL}/api/v1/copilot/handover",
                            json={"session_id": st.session_state.session_id, "is_live_chat": new_live},
                            timeout=5,
                        )
                    except Exception:
                        pass
                    st.session_state.is_live_chat = new_live
                    st.rerun()

            with btn_col4:
                if st.button(
                    "❌ Từ chối/Chuyển",
                    use_container_width=True,
                    disabled=bool(recorded_act),
                ):
                    handle_agent_action("REJECT", None)

            if recorded_act:
                st.success(f"Đã ghi nhận quyết định kiểm duyệt: **{recorded_act}**")
        else:
            st.info("Chưa có câu hỏi nào từ khách hàng cần đối soát. Vui lòng gửi câu hỏi tại Tab 1.")

    # -------------------------------------------------------------------------
    # RIGHT COLUMN: Copilot Intelligence & Audit Inspector
    # -------------------------------------------------------------------------
    with col_inspector:
        st.markdown("#### 🔍 Hồ Sơ Đối Soát & Dữ Liệu Căn Cứ (Copilot Inspector)")

        if current_resp:
            intent_info = current_resp.get("intent", {})
            guard_info = current_resp.get("guardrail", {})
            citations = current_resp.get("citations", [])
            order_data = current_resp.get("order_data")
            active_facts = current_resp.get("active_facts", {})
            context_summary = current_resp.get("context_summary", "")
            input_type = current_resp.get("input_type", "GENERAL")
            guard_action = guard_info.get("action_type", "UNKNOWN")
            guard_reason = guard_info.get("reason", "")

            # -----------------------------------------------------------------
            # 1. Guardrail Safety Status Banner (5 Scenarios)
            # -----------------------------------------------------------------
            if guard_action == "BLOCKED_FINANCIAL_TASK":
                st.markdown(
                    f"""
                    <div class="guard-banner-red">
                        <b style="color: #ef4444; font-size: 15px;">🚨 RỦI RO TÀI CHÍNH / HÀNH ĐỘNG HỆ THỐNG</b><br/>
                        <span style="font-size: 13.5px;">{guard_reason}</span><br/>
                        <span style="font-size: 12px; color: gray;">
                        <b>Quy tắc an toàn:</b> LLM bị KHÓA hoàn toàn tự động hoàn tiền/hủy đơn. Chuyên viên PHẢI xác minh thủ công tình trạng thanh toán và hàng hóa bên dưới.
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            elif guard_action == "LOW_CONFIDENCE_ESCALATE":
                st.markdown(
                    f"""
                    <div class="guard-banner-yellow">
                        <b style="color: #f59e0b; font-size: 15px;">⚠️ ĐỘ TỰ TIN THẤP ({intent_info.get('confidence', 0):.1%})</b><br/>
                        <span style="font-size: 13.5px;">{guard_reason}</span><br/>
                        <span style="font-size: 12px; color: gray;">
                        <b>Hướng dẫn:</b> Không phỏng đoán bừa. Chỉ hỏi khách để bổ sung thông tin còn thiếu (Mã đơn ORD-XXXX, mã sản phẩm).
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            elif guard_action == "ESCALATE_HUMAN" or current_resp.get("is_live_chat"):
                st.markdown(
                    f"""
                    <div class="guard-banner-blue">
                        <b style="color: #3b82f6; font-size: 15px;">🎧 KHÁCH YÊU CẦU GẶP CHUYÊN VIÊN TRỰC TIẾP</b><br/>
                        <span style="font-size: 13.5px;">{guard_reason or 'Khách hàng có nguyện vọng trao đổi với nhân viên hỗ trợ.'}</span><br/>
                        <span style="font-size: 12px; color: gray;">
                        <b>Trạng thái:</b> Đã ngắt bot tự động. Bạn đang kết nối trực tiếp với khách qua khung chat bên trái.
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            elif any(not doc.get("is_active", True) for doc in citations):
                st.markdown(
                    """
                    <div class="guard-banner-yellow">
                        <b style="color: #f59e0b; font-size: 15px;">📜 BẪY CHÍNH SÁCH CŨ / HẾT HIỆU LỰC PHÁT HIỆN</b><br/>
                        <span style="font-size: 13.5px;">Phát hiện tài liệu tra cứu có điều khoản đã hết hạn. Hãy trả lời dựa trên chính sách hiện hành.</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""
                    <div class="guard-banner-green">
                        <b style="color: #10b981; font-size: 15px;">✅ TRUY VẤN HỢP LỆ & AN TOÀN (HAPPY PATH)</b><br/>
                        <span style="font-size: 13.5px;">Ý định: <b>{intent_info.get('intent', 'N/A')}</b> · Tự tin: <b>{intent_info.get('confidence', 0):.1%}</b> · RAG đối soát đạt chuẩn.</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # -----------------------------------------------------------------
            # 2. Order Information Card
            # -----------------------------------------------------------------
            with st.expander("📦 Dữ Liệu Đơn Hàng Đối Soát", expanded=bool(order_data)):
                if order_data:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Mã đơn", order_data.get("order_id", "N/A"))
                    c2.metric("Khách hàng", order_data.get("customer_id", "N/A"))
                    c3.metric("Tổng tiền", f"{order_data.get('total_amount', 0):,} đ")

                    s1, s2, s3 = st.columns(3)
                    s1.write(f"**Trạng thái:** `{order_data.get('order_status', 'N/A')}`")
                    s2.write(f"**Thanh toán:** `{order_data.get('payment_status', 'N/A')}`")
                    s3.write(f"**Vận chuyển:** `{order_data.get('carrier', 'N/A')}`")

                    if "items" in order_data:
                        st.markdown("**Sản phẩm trong đơn:**")
                        st.table(pd.DataFrame(order_data["items"]))

                    if "shipping_timeline" in order_data:
                        with st.expander("Xem tiến trình giao hàng chi tiết"):
                            st.json(order_data["shipping_timeline"])
                else:
                    st.info("Không có mã đơn hàng nào được nhận diện trong lượt tương tác này.")

            # -----------------------------------------------------------------
            # 3. Policy Citations Card
            # -----------------------------------------------------------------
            with st.expander("📚 Căn Cứ Chính Sách & Điều Khoản RAG", expanded=bool(citations)):
                if citations:
                    for doc in citations:
                        is_active = doc.get("is_active", True)
                        badge_status = (
                            '<span class="badge-pill badge-green">🟢 CÒN HIỆU LỰC</span>'
                            if is_active
                            else '<span class="badge-pill badge-red">🔴 HẾT HIỆU LỰC</span>'
                        )
                        st.markdown(
                            f"""
                            <div style="border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px;">
                                <b>[{doc.get('doc_id')}] {doc.get('title')}</b> (v{doc.get('version', 1)}) · {badge_status}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        with st.expander(f"Xem nội dung trích lục: {doc.get('doc_id')}"):
                            st.write(doc.get("content", ""))
                else:
                    st.info("Không có tài liệu chính sách nào được trích dẫn.")

            # -----------------------------------------------------------------
            # 4. Context & Fact Memory Card
            # -----------------------------------------------------------------
            with st.expander("🧠 Bộ Nhớ Ngắn Hạn & Fact Hội Thoại", expanded=True):
                st.write("**Fact đã nhận diện:**")
                st.json(active_facts or {"ghi_chu": "Chưa có fact đặc thù"})
                st.write("**Phân loại câu nói:**", f"`{input_type}`")
                st.write("**Tóm tắt ngữ cảnh (Context Summary):**")
                st.info(context_summary or "Chưa có tóm tắt tích lũy.")

            # Top candidate intents
            probs = intent_info.get("all_probabilities", {})
            if probs:
                with st.expander("Phân phối xác suất Ý định (Top 3)"):
                    sorted_p = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:3]
                    df_p = pd.DataFrame(sorted_p, columns=["Ý định", "Xác suất"])
                    df_p["Xác suất"] = df_p["Xác suất"].apply(lambda v: f"{v:.1%}")
                    st.table(df_p)
        else:
            st.info("Bảng đối soát sẽ tự động cập nhật khi có tin nhắn từ khách hàng.")


# =============================================================================
# TAB 3: Telemetry & Safety Audit Dashboard
# =============================================================================
with tab_audit:
    st.markdown("### 📊 Báo cáo Kiểm toán An toàn AI & Hiệu năng Vận hành")
    st.caption("Dữ liệu trực tiếp từ Telemetry Service (:8003) qua Gateway (:8000)")

    if st.button("🔄 Làm mới số liệu kiểm toán", type="secondary"):
        st.rerun()

    try:
        stats_resp = requests.get(f"{GATEWAY_URL}/api/v1/copilot/stats", timeout=5)
        if stats_resp.status_code == 200:
            stats = stats_resp.json()

            total_interactions = stats.get("total_interactions", 0)
            avg_latency = stats.get("average_latency_ms", 0.0)
            actions_breakdown = stats.get("actions_breakdown", {})
            safety_block_rate = stats.get("safety_block_rate", 100.0)
            false_escalation_rate = stats.get("false_escalation_rate", 0.0)
            recent_records = stats.get("recent_records", [])

            # High-level KPIs
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Tổng tương tác", total_interactions)
            k2.metric("Thời gian phản hồi TB", f"{avg_latency:.1f} ms")
            k3.metric("Tỷ lệ Chặn Nguy Hại", f"{safety_block_rate:.1f}%", help="Mục tiêu: 100% chặn rủi ro tài chính/bẫy chính sách cũ")
            k4.metric("Tỷ lệ Chuyển Người Thật Sai", f"{false_escalation_rate:.1f}%", help="Mục tiêu: < 5% chuyển nhầm")

            st.markdown("---")
            c_chart, c_table = st.columns([1, 2])

            with c_chart:
                st.markdown("#### Phân bổ Quyết định Nhân viên")
                if actions_breakdown:
                    df_actions = pd.DataFrame(
                        list(actions_breakdown.items()),
                        columns=["Hành động", "Số lượng"],
                    )
                    st.bar_chart(df_actions.set_index("Hành động"))
                else:
                    st.info("Chưa có hành động thẩm định nào được ghi nhận.")

            with c_table:
                st.markdown("#### Nhật ký Tương tác Gần nhất")
                if recent_records:
                    df_recent = pd.DataFrame(recent_records)
                    cols_to_show = [
                        col
                        for col in [
                            "interaction_id",
                            "customer_query",
                            "predicted_intent",
                            "guardrail_action",
                            "human_action",
                            "latency_ms",
                        ]
                        if col in df_recent.columns
                    ]
                    st.dataframe(df_recent[cols_to_show], use_container_width=True, height=320)
                else:
                    st.info("Chưa có nhật ký tương tác trong cơ sở dữ liệu.")
        else:
            st.error(f"Lỗi truy vấn Telemetry: {stats_resp.text}")
    except Exception as ex:
        st.warning(f"Chưa kết nối được với Telemetry Service: {ex}")
