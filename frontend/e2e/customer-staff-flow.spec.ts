/**
 * Layer 3 Browser E2E Test Specification (Playwright)
 * Covers the full user journey across `/` (Role Switcher), `/customer` (Customer Portal), and `/staff` (Staff Workbench).
 */
export const E2E_SCENARIOS = [
  {
    id: 'E2E-01',
    name: 'Role Switcher Navigation (/ -> /customer and / -> /staff)',
    steps: [
      'Open / and verify both role cards ("Tôi là Khách hàng", "Tôi là Nhân viên") render',
      'Click "Tôi là Khách hàng" -> URL changes to /customer, customer dropdown & chat stream load',
      'Click "Đổi vai trò" -> URL returns to /, click "Tôi là Nhân viên" -> URL changes to /staff',
    ],
  },
  {
    id: 'E2E-02',
    name: 'Customer Portal Scroll Lock, Messenger Quote & Policy Viewer Modal ([POL-XXX] with X button)',
    steps: [
      'On /customer, verify outer container has h-screen overflow-hidden and chat container has overscroll-contain',
      'Send customer question -> verify immediate acknowledgement and Messenger-style faded quote above reply',
      'Click [POL-RET-001] badge -> verify Policy Document Modal opens with full policy content and closes on clicking X button',
    ],
  },
  {
    id: 'E2E-03',
    name: 'Staff Workbench Priority Queue (Newest Question at Top) & Perspective Bubble Colors',
    steps: [
      'On /staff, verify customer with newest question / pending Copilot draft is sorted to index 0 with "MỚI NHẤT" / "Chờ duyệt" badge',
      'Verify Customer messages render on LEFT in WHITE and Staff messages render on RIGHT in BLUE',
      'Verify Messenger-style faded quote appears at top of Copilot Draft preview card and above each Staff reply bubble',
    ],
  },
];
