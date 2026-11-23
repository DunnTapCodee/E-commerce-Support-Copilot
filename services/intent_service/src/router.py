"""Fast deterministic VI/EN language routing, fitted on training data only."""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

VI_CHARS = re.compile(r"[ăâđêôơưàáạảãằắặẳẵầấậẩẫèéẹẻẽềếệểễìíịỉĩòóọỏõồốộổỗờớợởỡùúụủũừứựửữỳýỵỷỹ]", re.I)
# Used only by standalone detect_language; production loads the fitted vocabulary.
VI_NOTONE = frozenset('toi muon huy don hang hoan tien phi bao nhieu giao chua khong minh nay giup voi duoc cho nhan vien chinh sach doi tra san pham kiem tinh trang'.split())
THRESHOLD = 0.2


class LanguageRouter:
    def __init__(self, vocabulary=VI_NOTONE, threshold=THRESHOLD):
        self.vocabulary = frozenset(vocabulary)
        self.threshold = float(threshold)

    @classmethod
    def load(cls, path: Path):
        meta = json.loads((path / 'meta.json').read_text())
        return cls((path / 'vi_notone.txt').read_text().splitlines(), meta['threshold'])

    def detect(self, text: str) -> str:
        if VI_CHARS.search(text):
            return 'vi'
        tokens = re.findall('[a-z]+', text.lower())
        if not tokens:
            return 'en'
        return 'vi' if sum(t in self.vocabulary for t in tokens) / len(tokens) >= self.threshold else 'en'


def detect_language(text: str) -> str:
    return LanguageRouter().detect(text)


def main():
    """Fit vocabulary/threshold on train/val, then report held-out accuracy."""
    import time
    import numpy as np
    import pandas as pd
    from sklearn.metrics import accuracy_score, confusion_matrix
    from services.intent_service.src.pipeline.data.augment_vi import no_diacritic
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, default=Path('data/processed/module1'))
    parser.add_argument('--output', type=Path, default=Path('artifacts/models/intent/router'))
    args = parser.parse_args()
    en = pd.read_parquet(args.data_dir / 'train_en.parquet')
    vi = pd.read_parquet(args.data_dir / 'train_vi.parquet')
    en_vocab = set(re.findall('[a-z]+', ' '.join(en.text).lower()))
    counts = Counter(re.findall('[a-z]+', ' '.join(no_diacritic(t) for t in vi[vi.aug_type == 'orig'].text).lower()))
    vocab = [word for word, _ in counts.most_common() if word not in en_vocab][:300]
    val_en = pd.read_parquet(args.data_dir / 'val_en.parquet')
    val_vi = pd.read_parquet(args.data_dir / 'val_vi.parquet')
    texts = list(val_en.text) + list(val_vi.text) + [no_diacritic(t) for t in val_vi.text]
    labels = ['en'] * len(val_en) + ['vi'] * (2 * len(val_vi))
    threshold = max(np.arange(.1, .601, .05), key=lambda x: accuracy_score(labels, [LanguageRouter(vocab, x).detect(t) for t in texts]))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'vi_notone.txt').write_text('\n'.join(vocab) + '\n')
    (args.output / 'meta.json').write_text(json.dumps({'threshold': float(threshold), 'seed': 42}, indent=2))
    router = LanguageRouter(vocab, threshold)
    evaluation = pd.read_parquet(args.data_dir / 'router_eval.parquet')
    timings, predictions = [], []
    for text in evaluation.text:
        start = time.perf_counter(); predictions.append(router.detect(text)); timings.append((time.perf_counter() - start) * 1000)
    mask = evaluation.aug_type == 'no_diacritic'
    overall = accuracy_score(evaluation.lang, predictions)
    unaccented = accuracy_score(evaluation.loc[mask, 'lang'], np.array(predictions)[mask])
    p95 = float(np.percentile(timings, 95))
    report = Path('reports/module1/router.md'); report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(f'# Router\n\nAccuracy: {overall:.4f}\n\nVI không dấu: {unaccented:.4f}\n\np95: {p95:.5f} ms\n\nConfusion [en, vi]: {confusion_matrix(evaluation.lang, predictions, labels=["en", "vi"]).tolist()}\n')
    if overall < .98 or unaccented < .95 or p95 >= .1:
        raise SystemExit('Router acceptance criteria not met; see reports/module1/router.md')


if __name__ == '__main__':
    main()
