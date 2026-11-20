"""Train baseline ML (TF-IDF word+char n-gram + LinearSVC hiệu chỉnh) trên dataset.jsonl và so với LLM.

Chạy: python data/intent_eval/train_ml.py [--save artifacts/models/intent_vi.pkl]
Cần: scikit-learn, joblib. Chia train/test 80/20 phân tầng (stratified) TRƯỚC mọi xử lý để tránh rò rỉ.
"""
import argparse
import json
import sys
from pathlib import Path

import joblib
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from merge import LABELS  # noqa: E402


def build() -> Pipeline:
    feats = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, lowercase=True)),
        # char n-gram giúp chịu được teencode, lỗi gõ, không dấu
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, lowercase=True)),
    ])
    clf = CalibratedClassifierCV(LinearSVC(C=0.5, class_weight="balanced"), cv=3)
    return Pipeline([("feats", feats), ("clf", clf)])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", default="")
    args = ap.parse_args()

    rows = [json.loads(l) for l in (HERE / "dataset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    X = [r["text"] for r in rows]
    y = [r["intent"] for r in rows]
    ids = [r["id"] for r in rows]
    X_tr, X_te, y_tr, y_te, _, id_te = train_test_split(X, y, ids, test_size=0.2, stratify=y, random_state=42)

    pipe = build()
    cv = cross_val_score(pipe, X_tr, y_tr, cv=StratifiedKFold(5, shuffle=True, random_state=42), scoring="f1_macro")
    print(f"CV Macro-F1 (train 80%): {cv.mean():.4f} ± {cv.std():.4f}")

    pipe.fit(X_tr, y_tr)
    pred = pipe.predict(X_te)
    print(f"Holdout Macro-F1: {f1_score(y_te, pred, average='macro'):.4f}")
    print(classification_report(y_te, pred, labels=LABELS, zero_division=0))

    # So sánh LLM trên cùng tập test (nếu đã chạy eval_llm.py)
    for res in HERE.glob("results_*.jsonl"):
        llm = {json.loads(l)["id"]: json.loads(l)["pred"] for l in res.read_text(encoding="utf-8").splitlines()}
        pairs = [(llm[i], t) for i, t in zip(id_te, y_te) if i in llm]
        if pairs:
            acc = sum(p == t for p, t in pairs) / len(pairs)
            print(f"[So sánh] {res.stem} trên cùng tập test ({len(pairs)} câu): accuracy {acc:.2%}")

    if args.save:
        pipe.fit(X, y)  # fit lại trên toàn bộ dữ liệu
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipe, args.save)
        print(f"Đã lưu model -> {args.save}")


if __name__ == "__main__":
    main()
