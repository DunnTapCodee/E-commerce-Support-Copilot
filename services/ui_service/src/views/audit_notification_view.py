"""Audit & Change Notification View: Real-time Document Mutation Feed, Diff Viewer & 1-Click Rollback."""
import requests
import streamlit as st


def render_audit_notification_view(gateway_url: str):
    st.markdown("### 🔔 Thông báo & Nhật ký Biến động Tài liệu Chính sách")
    st.caption("Bất kỳ sự thay đổi nào đối với tài liệu (tạo mới, đổi ngày, tự động hết hạn, rollback) đều được ghi nhận tức thì tại đây.")

    col_title, col_refresh = st.columns([4, 1])
    with col_refresh:
        if st.button("🔄 Làm mới thông báo", use_container_width=True):
            st.rerun()

    # Fetch audit logs
    audit_logs = []
    try:
        resp = requests.get(f"{gateway_url}/api/v1/copilot/policies/audit-logs", timeout=10.0)
        if resp.status_code == 200:
            audit_logs = resp.json()
    except Exception as e:
        st.error(f"Không thể tải nhật ký thông báo: {str(e)}")

    if not audit_logs:
        st.info("Chưa có biến động tài liệu nào được ghi nhận.")
        return

    # Metrics Summary
    total_logs = len(audit_logs)
    auto_events = sum(1 for l in audit_logs if l.get("action") in ("AUTO_EXPIRE", "AUTO_ACTIVATE"))
    human_edits = sum(1 for l in audit_logs if l.get("action") in ("CREATE", "UPDATE", "SUPERSEDE"))
    rollbacks = sum(1 for l in audit_logs if l.get("action") == "ROLLBACK")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tổng sự kiện biến động", total_logs)
    c2.metric("Chỉnh sửa bởi Nhân viên", human_edits)
    c3.metric("Tự động hóa hệ thống (Auto)", auto_events)
    c4.metric("Lượt hoàn tác (Rollback)", rollbacks)

    st.divider()

    # Change Notification Feed
    st.markdown("#### 📜 Dòng thời gian thông báo thay đổi (Notification Feed)")

    for log in audit_logs:
        log_id = log.get("log_id")
        action = log.get("action", "UPDATE")
        timestamp = log.get("timestamp")
        doc_id = log.get("doc_id")
        doc_title = log.get("doc_title") or "N/A"
        actor = log.get("performed_by", "Admin")
        reason = log.get("reason", "")
        before_snap = log.get("before_snapshot")
        after_snap = log.get("after_snapshot")

        # Color and icon by action
        if action == "CREATE":
            color_badge = "🟢 [TẠO MỚI]"
        elif action == "UPDATE":
            color_badge = "🟡 [CHỈNH SỬA]"
        elif action == "AUTO_EXPIRE":
            color_badge = "🔴 [TỰ ĐỘNG HẾT HẠN]"
        elif action == "AUTO_ACTIVATE":
            color_badge = "🟢 [TỰ ĐỘNG KÍCH HOẠT]"
        elif action == "SUPERSEDE":
            color_badge = "⚫ [ĐÃ THAY THẾ]"
        elif action == "ROLLBACK":
            color_badge = "🟣 [HOÀN TÁC ROLLBACK]"
        elif action == "DELETE":
            color_badge = "❌ [XÓA]"
        else:
            color_badge = f"⚪ [{action}]"

        with st.container():
            st.markdown(f"**{color_badge}** `{doc_id}` — **{doc_title}**")
            st.caption(f"⏱️ **Thời gian:** {timestamp} | 👤 **Thực hiện bởi:** `{actor}` | 🔑 **Mã log:** `{log_id}`")
            st.markdown(f"> **Chi tiết biến động:** {reason}")

            # Collapsible Before / After Snapshot Diff
            with st.expander("🔍 Xem chi tiết thay đổi (Before / After Snapshot)"):
                col_b, col_a = st.columns(2)
                with col_b:
                    st.markdown("**Trạng thái trước thay đổi (Before):**")
                    if before_snap:
                        st.json({
                            "title": before_snap.get("title"),
                            "is_active": before_snap.get("is_active"),
                            "policy_type": before_snap.get("policy_type"),
                            "effective_date": before_snap.get("effective_date"),
                            "expiration_date": before_snap.get("expiration_date"),
                        })
                    else:
                        st.text("(Chưa có dữ liệu - Tài liệu mới tạo)")
                with col_a:
                    st.markdown("**Trạng thái sau thay đổi (After):**")
                    if after_snap:
                        st.json({
                            "title": after_snap.get("title"),
                            "is_active": after_snap.get("is_active"),
                            "policy_type": after_snap.get("policy_type"),
                            "effective_date": after_snap.get("effective_date"),
                            "expiration_date": after_snap.get("expiration_date"),
                        })
                    else:
                        st.text("(Đã xóa tài liệu)")

            # One-click Rollback Button (only if before snapshot exists)
            if before_snap and action != "ROLLBACK":
                col_rb1, _ = st.columns([2, 5])
                with col_rb1:
                    if st.button(f"⏪ Hoàn tác về phiên bản này (Rollback)", key=f"btn_rb_{log_id}"):
                        with st.spinner("Đang thực hiện hoàn tác chính sách..."):
                            try:
                                rb_payload = {
                                    "log_id": log_id,
                                    "performed_by": "Nhân viên CSKH (Rollback)",
                                    "reason": f"Hoàn tác thay đổi của log {log_id}",
                                }
                                resp = requests.post(
                                    f"{gateway_url}/api/v1/copilot/policies/rollback",
                                    json=rb_payload,
                                    timeout=20.0,
                                )
                                if resp.status_code == 200:
                                    st.success(f"Đã hoàn tác chính sách [{doc_id}] thành công!")
                                    st.rerun()
                                else:
                                    st.error(f"Lỗi rollback: {resp.text}")
                            except Exception as e:
                                st.error(f"Lỗi: {str(e)}")

            st.markdown("---")
