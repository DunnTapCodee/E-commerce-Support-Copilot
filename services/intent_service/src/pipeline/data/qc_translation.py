"""Translation QC with strict slots, paired embedding cosine and auditable rejection."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
from services.intent_service.src.pipeline.data.placeholders import restore, SLOT, TOKEN
from services.intent_service.src.pipeline.dataset import ALL_BITEXT_INTENTS

ENGLISH = set('the this that these those please where when what how my your want would could should refund shipping return product order payment account cancel help store delivery have with from about does not is are you can'.split())
PAIR_INTENTS = {'return_product_online','return_product_in_store','availability_online','availability_in_store','exchange_product','exchange_product_in_store','track_order','track_delivery','refund_policy','return_policy'}


def prepare_pairs(english, translated, join):
    """Expand unique translations to source rows; restore slots before semantic QC."""
    translated = translated.rename(columns={'src_id': 'translation_id'})
    merged = english.merge(join, on='src_id', validate='one_to_one').merge(translated.drop(columns=['text_en'], errors='ignore'), on='translation_id', how='left', validate='many_to_one')
    if merged.text_vi.isna().any():
        raise ValueError('Translations missing; finish k01 and download its output')
    rows = []
    from services.intent_service.src.pipeline.data.placeholders import protect
    for row in merged.to_dict('records'):
        mapping = protect(row['text'])[1]
        for candidate in ('text_vi','vi_para_1','vi_para_2'):
            value = row.get(candidate)
            if not isinstance(value,str) or not value.strip():
                continue
            restored, lost = restore(value, mapping)
            rows.append({**row, 'candidate': candidate, 'text_en': row['text'], 'candidate_text': restored, 'qc_slot_lost': lost})
    return pd.DataFrame(rows)


def quality_checks(frame, cosines):
    result = frame.copy()
    if len(cosines) != len(result):
        raise ValueError('QC cosine count does not match candidate rows')
    result['qc_cos'] = np.asarray(cosines)
    result['qc_len_ratio'] = result.candidate_text.str.len() / result.text_en.str.len().clip(lower=1)
    def untranslated(text):
        words = re.findall(r'\b[^\W\d_]+\b', SLOT.sub('', text).lower())
        return sum(w.isascii() and w in ENGLISH for w in words) / max(1,len(words)) > .5
    result['qc_untranslated'] = result.candidate_text.map(untranslated)
    result['qc_flag'] = result.qc_slot_lost | result.qc_untranslated | (result.qc_cos < .70) | ~np.isfinite(result.qc_cos) | (result.qc_len_ratio < .5) | (result.qc_len_ratio > 2.5)
    return result


def finalize_qc(frame, cosines, output):
    output.with_suffix('.qc.json').unlink(missing_ok=True)
    checked = quality_checks(frame, cosines)
    passed = checked[~checked.qc_flag]
    priority = {'text_vi':0,'vi_para_1':1,'vi_para_2':2}
    chosen = passed.assign(priority=passed.candidate.map(priority)).sort_values(['src_id','priority']).drop_duplicates('src_id').copy()
    chosen['text'] = chosen.candidate_text
    # Only separately validated candidates can become training paraphrases.
    paras = passed[passed.candidate != 'text_vi'].groupby('src_id').candidate_text.apply(list).to_dict()
    chosen_text = chosen.set_index('src_id').text.to_dict()
    chosen['paraphrases'] = chosen.src_id.map(lambda sid: [p for p in paras.get(sid,[]) if p != chosen_text[sid]][:2])
    chosen['lang'] = 'vi'
    output.parent.mkdir(parents=True, exist_ok=True)
    chosen.to_parquet(output,index=False)
    report = Path('reports/module1');report.mkdir(parents=True,exist_ok=True)
    checked[checked.qc_flag].to_csv(report/'translation_rejected.csv',index=False)
    original = checked[checked.candidate == 'text_vi']
    by_intent = original.groupby('intent').qc_flag.agg(['mean','count'])
    samples = pd.concat([g.sample(n=min(5,len(g)),random_state=42) for _,g in original.groupby('intent')], ignore_index=True)
    def table(df):
        return df.to_csv(index=True)
    total = original.src_id.nunique(); rate = len(chosen)/max(1,total)
    counts = chosen[chosen.intent.isin(ALL_BITEXT_INTENTS)].intent.value_counts().reindex(ALL_BITEXT_INTENTS,fill_value=0)
    (report/'translation_qc.md').write_text('# Translation QC\n\nAccepted after recovery: '+f'{len(chosen)}/{total} ({rate:.2%})\n\nFlag rate by intent:\n```csv\n'+table(by_intent)+'```\n\n10 flagged examples:\n```csv\n'+table(checked[checked.qc_flag][['intent','text_en','candidate_text','qc_cos','qc_slot_lost']].head(10))+'```\n\nFive random samples per intent:\n```csv\n'+table(samples)+'```\n\nConfusable intent pairs:\n```csv\n'+table(original[original.intent.isin(PAIR_INTENTS)].groupby('intent',group_keys=False).head(5)[['intent','text_en','candidate_text']])+'```\n')
    if rate < .95 or counts.min() < 800:
        raise SystemExit('Translation QC gate failed (<95% accepted or an intent has <800 rows); review report before continuing')
    output.with_suffix('.qc.json').write_text(json.dumps({'passed': True, 'rows': len(chosen), 'accepted_ratio': rate, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}, indent=2))
    return chosen


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pairs',type=Path,default=Path('data/interim/qc_pairs.parquet'))
    parser.add_argument('--cosines',type=Path,required=True,help='qc_cos.npy produced by k03')
    parser.add_argument('--output',type=Path,default=Path('data/interim/bitext_vi_qc.parquet'))
    args=parser.parse_args()
    finalize_qc(pd.read_parquet(args.pairs),np.load(args.cosines),args.output)


if __name__=='__main__':
    main()
