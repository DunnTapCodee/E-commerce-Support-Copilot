"""CLINC OOS collection and explicitly reviewed Vietnamese QA categories."""
import hashlib
from pathlib import Path
import pandas as pd
from services.intent_service.src.pipeline.data.load_bitext import group_id
from services.intent_service.src.preprocessing import normalize_text


def load_clinc():
    from datasets import load_dataset
    dataset = load_dataset('clinc_oos', 'plus')
    rows = []
    for split in dataset.values():
        names = split.features['intent'].names
        rows.extend({'text': r['text']} for r in split if names[r['intent']] == 'oos')
    frame = pd.DataFrame(rows).drop_duplicates('text').sort_values('text')
    frame = frame.sample(n=min(1200,len(frame)),random_state=42).sort_values('text').reset_index(drop=True)
    frame['text'] = frame.text.map(normalize_text)
    frame['src_id'] = ['o' + hashlib.sha256(t.encode()).hexdigest()[:16] for t in frame.text]
    frame['group_id'] = frame.text.map(group_id)
    frame['intent'] = 'out_of_scope'; frame['lang'] = 'en'; frame['source'] = 'clinc_oos'
    frame['category'] = 'OOS'; frame['tags'] = ''
    return frame


def inspect_qa(path):
    frame = pd.read_csv(path, encoding='utf-8-sig')
    print(frame.type.value_counts().to_string())
    print(frame[['question','type']].head(20).to_string(index=False))
    return frame


def select_qa(path, selection):
    """selection maps explicitly reviewed type names to written selection reasons."""
    frame = inspect_qa(path)
    if not selection or any(not str(reason).strip() for reason in selection.values()):
        raise ValueError('Provide reviewed QA types and reasons; type names alone are not proof of OOS')
    if set(selection) - set(frame.type):
        raise ValueError('Unknown QA type')
    frame = frame[frame.type.isin(selection)].drop_duplicates('question').sort_values('question')
    frame = frame.sample(n=min(300,len(frame)),random_state=42).copy()
    frame['text'] = frame.question.map(normalize_text)
    frame['src_id'] = ['q' + hashlib.sha256(t.encode()).hexdigest()[:16] for t in frame.text]
    frame['group_id'] = frame.text.map(group_id)
    frame['intent'] = 'out_of_scope'; frame['lang'] = 'vi'; frame['source'] = 'reviewed_qa'
    frame['category'] = 'OOS'; frame['tags'] = ''
    report = Path('reports/module1/oos_selection.md'); report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text('# Reviewed QA selection\n\n' + '\n'.join(f'- {key}: {reason}' for key,reason in selection.items()))
    return frame[['src_id','group_id','text','intent','lang','source','category','tags']]
