import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.intent_service.src.predictor import IntentPredictor

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

p = IntentPredictor()
print("Predictor initialized successfully.")
print("Routing mode:", p.routing_mode)
print("Total classes:", p.models)

queries = [
    "I want to track my order status",
    "What is your return policy?",
    "Please connect me to a human agent",
    "I have a payment problem with my card",
    "Random gibberish asdkjasdkj 1234",
    "Tôi muốn theo dõi đơn hàng"
]

print("\n--- Predictions ---")
for q in queries:
    resp = p.predict(q)
    print(f"Q: '{q}'\n  -> Intent: [{resp.intent}] | Conf: {resp.confidence:.1%} | InScope: {resp.is_in_scope}")
