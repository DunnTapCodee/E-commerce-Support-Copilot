"""Download Bitext instructions only, audit labels/slots and group near-duplicates."""
import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
import pandas as pd
from services.intent_service.src.preprocessing import normalize_text
from services.intent_service.src.pipeline.dataset import ALL_BITEXT_INTENTS
from services.intent_service.src.pipeline.data.placeholders import SLOT, protect, slot_kind


def norm_key(text):
    text = SLOT.sub(' slot ', normalize_text(text).lower())
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', text)).strip()


def group_id(text):
    return 'g' + hashlib.sha256(norm_key(text).encode()).hexdigest()[:20]


def load_bitext(raw_dir=Path('data/raw/bitext'), output=Path('data/interim/bitext_en.parquet')):
    from datasets import load_dataset
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / 'bitext_raw.parquet'
    if raw_path.exists():
        frame = pd.read_parquet(raw_path, columns=['instruction', 'intent', 'category', 'tags'])
    else:
        frame = load_dataset('bitext/Bitext-retail-ecommerce-llm-chatbot-training-dataset', split='train').select_columns(['instruction', 'intent', 'category', 'tags']).to_pandas()
        frame.to_parquet(raw_path, index=False)
    actual = set(frame.intent)
    if actual != set(ALL_BITEXT_INTENTS):
        raise ValueError(f'Bitext label mismatch: missing={set(ALL_BITEXT_INTENTS)-actual}; extra={actual-set(ALL_BITEXT_INTENTS)}')
    frame = frame.rename(columns={'instruction': 'text'})
    frame['text'] = frame.text.map(normalize_text)
    frame['src_id'] = [f'b{i:06}' for i in range(len(frame))]
    frame['group_id'] = frame.text.map(group_id)
    frame['lang'] = 'en'; frame['source'] = 'bitext'
    # Ambiguous normalized utterances must never train contradictory targets.
    conflicting = frame.groupby('group_id').intent.nunique()
    if (conflicting > 1).any():
        raise ValueError(f'{sum(conflicting > 1)} normalized groups have conflicting labels; resolve before splitting')
    placeholders = Counter(slot for text in frame.text for slot in SLOT.findall(text))
    report = Path('reports/module1'); report.mkdir(parents=True, exist_ok=True)
    mapping, unmapped = {}, []
    for slot in sorted(placeholders):
        try:
            mapping[slot] = {'count': placeholders[slot], 'kind': slot_kind(slot)}
        except ValueError:
            unmapped.append(slot); mapping[slot] = {'count': placeholders[slot], 'kind': None}
    (report / 'placeholders.json').write_text(json.dumps(mapping, ensure_ascii=False, indent=2))
    print(frame.intent.value_counts().sort_index().to_string()); print('groups:', frame.group_id.nunique()); print(mapping)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output, index=False)
    if unmapped:
        raise ValueError(f'Extend explicit placeholder mapping before translation: {unmapped}')
    return frame


def translation_input(frame):
    """One protected request per unique text, plus a source-id join table."""
    unique = frame.drop_duplicates('text').copy()
    unique['text_en'] = unique.text.map(lambda text: protect(text)[0])
    unique['slot_mapping'] = unique.text.map(lambda text: json.dumps(protect(text)[1], ensure_ascii=False))
    join = frame[['src_id', 'text']].merge(unique[['src_id', 'text']].rename(columns={'src_id': 'translation_id'}), on='text', validate='many_to_one')
    unique['translation_id'] = unique.src_id
    return unique, join[['src_id', 'translation_id']]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.parse_args()
    load_bitext()
