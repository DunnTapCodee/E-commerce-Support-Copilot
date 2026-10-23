import joblib
import numpy as np
import sys
from pathlib import Path
from scipy.special import softmax

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

model_dir = Path("artifacts/models/legacy_linearsvc_en")
le = joblib.load(model_dir / "label_encoder_full.pkl")
vec = joblib.load(model_dir / "tfidf_vectorizer_full.pkl")
model = joblib.load(model_dir / "model_intent_full.pkl")

test_queries = [
    # English queries (Bitext standard)
    "I want to track my order status",
    "Can I cancel my purchase order?",
    "How many days for delivery to my address?",
    "I want to return this product and get my money back",
    "I have a payment problem with my card",
    "Please connect me to a human agent",
    "Where is the physical store located?",
    "What is your return policy?",
    "Can you give me an invoice for my order?",
    "How do I recover my password?",
    # Vietnamese queries
    "Tôi muốn theo dõi đơn hàng",
    "Làm thế nào để hủy đơn hàng vừa đặt",
    "Chính sách đổi trả sản phẩm trong mấy ngày",
    "Phí ship giao hàng là bao nhiêu",
    "Cho tôi gặp nhân viên chăm sóc khách hàng",
    "Tôi muốn hoàn tiền vào tài khoản",
]

print("=== TESTING IMPORTED ML MODEL (LinearSVC - 46 CLASSES) ===")
for q in test_queries:
    X = vec.transform([q])
    pred_idx = model.predict(X)[0]
    intent_label = le.inverse_transform([pred_idx])[0]

    # Calculate confidence via softmax over decision_function
    if hasattr(model, "decision_function"):
        scores = model.decision_function(X)[0]
        probs = softmax(scores)
        conf = float(np.max(probs))
    else:
        conf = 1.0

    print(f"Q: '{q}'")
    print(f"   -> Intent: [{intent_label}] | Confidence: {conf:.2%}")
