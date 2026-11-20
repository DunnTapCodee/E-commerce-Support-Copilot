"""Gộp các file parts/*.jsonl thành dataset.jsonl (gán id, kiểm tra trùng lặp, thống kê)."""
import json
import random
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
LABELS = [
    "track_order", "cancel_order", "delivery_time", "delivery_issue", "shipping_costs",
    "return_policy", "return_product", "refund_policy", "request_refund", "refund_status",
    "payment_issue", "human_agent", "other_ecommerce", "out_of_scope",
]


def main() -> None:
    rows, seen = [], set()
    for f in sorted((HERE / "parts").glob("*.jsonl")):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            r = json.loads(line)
            key = " ".join(r["text"].lower().split())
            if r["intent"] not in LABELS:
                print(f"[skip] {f.name}:{n} nhãn lạ: {r['intent']}")
                continue
            if key in seen:
                print(f"[skip] {f.name}:{n} trùng: {r['text'][:60]}")
                continue
            seen.add(key)
            rows.append({"text": r["text"].strip(), "intent": r["intent"], "style": r.get("style", ""), "source": f.stem})

    random.Random(42).shuffle(rows)
    for i, r in enumerate(rows, 1):
        r["id"] = f"Q{i:04d}"
    out = HERE / "dataset.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({k: r[k] for k in ("id", "text", "intent", "style", "source")}, ensure_ascii=False) + "\n")

    print(f"Tổng: {len(rows)} câu -> {out}")
    for lab, c in sorted(Counter(r["intent"] for r in rows).items(), key=lambda x: LABELS.index(x[0])):
        print(f"  {lab:16s} {c}")
    print("Style:", Counter(r["style"] for r in rows).most_common(12))


if __name__ == "__main__":
    main()
