"""E-Commerce Support Copilot — Modular UI Application (Streamlit Native).
Thin Orchestrator routing to modular views in services/ui_service/src/views/.
"""
import os
import sys
import uuid
from pathlib import Path
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.ui_service.src.views.chat_view import render_chat_view
from services.ui_service.src.views.policy_view import render_policy_view
from services.ui_service.src.views.audit_notification_view import render_audit_notification_view
from services.ui_service.src.views.telemetry_view import render_telemetry_view

# Page Config
st.set_page_config(
    page_title="E-Commerce Support Copilot",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8000").rstrip("/")

# -----------------------------------------------------------------------------
# Session State Initialization
# -----------------------------------------------------------------------------
if "session_id" not in st.session_state:
    st.session_state.session_id = f"SES-{uuid.uuid4().hex[:8].upper()}"

# Custom CSS Styling
st.markdown(
    """
    <style>
    .main-header {
        font-size: 24px;
        font-weight: 700;
        color: #1e293b;
        margin-bottom: 8px;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 16px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        white-space: pre-wrap;
        font-size: 15px;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Sidebar Navigation
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/bot.png", width=64)
    st.title("Support Copilot")
    st.caption("Trợ lý CSKH & Quản trị tri thức thông minh")
    st.divider()

    selected_tab = st.radio(
        "Điều hướng hệ thống:",
        [
            "💬 Hội thoại CSKH & Copilot",
            "📋 Quản lý Chính sách (Policy Lifecycle)",
            "🔔 Thông báo & Lịch sử Tài liệu",
            "📊 Thống kê Hiệu năng (Telemetry)",
        ],
        index=0,
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

    st.divider()
    st.caption(f"Gateway URL: `{GATEWAY_URL}`")
    st.caption("Version: 2.1.0-modular")

# View Router
if selected_tab == "💬 Hội thoại CSKH & Copilot":
    render_chat_view(GATEWAY_URL)
elif selected_tab == "📋 Quản lý Chính sách (Policy Lifecycle)":
    render_policy_view(GATEWAY_URL)
elif selected_tab == "🔔 Thông báo & Lịch sử Tài liệu":
    render_audit_notification_view(GATEWAY_URL)
elif selected_tab == "📊 Thống kê Hiệu năng (Telemetry)":
    render_telemetry_view(GATEWAY_URL)
