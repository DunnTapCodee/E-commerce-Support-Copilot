"""Telemetry & System Performance Dashboard View."""
import requests
import streamlit as st


def render_telemetry_view(gateway_url: str):
    st.markdown("### 📊 Thống kê Hiệu năng Hệ thống & Giám sát An toàn (Telemetry)")
    st.caption("Tổng hợp chỉ số độ trễ, tỷ lệ can thiệp của nhân viên và phân bổ các chốt chặn an toàn (Guardrails).")

    stats = None
    try:
        resp = requests.get(f"{gateway_url}/api/v1/copilot/stats", timeout=10.0)
        if resp.status_code == 200:
            stats = resp.json()
    except Exception as e:
        st.error(f"Không thể kết nối Telemetry Service: {str(e)}")

    if not stats:
        st.info("Chưa có số liệu thống kê.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tổng lượt truy vấn (Queries)", stats.get("total_queries", 0))
    c2.metric("Tỷ lệ tự động phê duyệt", f"{stats.get('auto_approved_rate', 0.0):.1%}")
    c3.metric("Tỷ lệ chuyển nhân viên (Escalated)", f"{stats.get('escalation_rate', 0.0):.1%}")
    c4.metric("Độ trễ trung bình", f"{stats.get('avg_latency_ms', 0):.0f} ms")

    st.divider()

    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.markdown("#### 🎯 Phân bổ Ý định Khách hàng (Intent Distribution)")
        intent_dist = stats.get("intent_distribution", {})
        if intent_dist:
            st.bar_chart(intent_dist)
        else:
            st.write("Chưa có dữ liệu phân bổ ý định.")

    with col_chart2:
        st.markdown("#### 🛡️ Thống kê Chốt chặn Guardrails")
        guard_dist = stats.get("guardrail_actions", {})
        if guard_dist:
            st.bar_chart(guard_dist)
        else:
            st.write("Chưa có dữ liệu chốt chặn an toàn.")
