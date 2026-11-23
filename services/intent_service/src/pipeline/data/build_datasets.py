"""Prepare translation inputs, QC pairs, and deterministic bilingual dataset files."""
import argparse
import hashlib
import json
import random
from pathlib import Path
import numpy as np
import pandas as pd
from services.intent_service.src.pipeline.dataset import ALL_BITEXT_INTENTS, OOS_LABEL
from services.intent_service.src.pipeline.data.load_bitext import load_bitext, translation_input, group_id
from services.intent_service.src.pipeline.data.oos import load_clinc, inspect_qa, select_qa
from services.intent_service.src.pipeline.data.build_splits import build_splits
from services.intent_service.src.pipeline.data.placeholders import fill_slots
from services.intent_service.src.pipeline.data.augment_vi import augment as augment_vi, AUGMENTERS, no_diacritic
from services.intent_service.src.pipeline.data.augment_en import augment as augment_en
from services.intent_service.src.pipeline.data.qc_translation import prepare_pairs
from services.intent_service.src.preprocessing import normalize_text

COLUMNS = ['src_id','group_id','text','intent','lang','aug_type','split','source']
INTERIM = Path('data/interim')
OUT = Path('data/processed/module1')
REPORT = Path('reports/module1')


def prepare(qa_selection=None):
    INTERIM.mkdir(parents=True,exist_ok=True)
    bitext = load_bitext()
    english = pd.concat([bitext,load_clinc()],ignore_index=True).sort_values('src_id')
    english.to_parquet(INTERIM/'source_en.parquet',index=False)
    sources = english
    if not qa_selection:
        (INTERIM/'qa_vi.parquet').unlink(missing_ok=True)
    if qa_selection:
        qa=select_qa(Path('data/raw/Vietnamese-Customer-Support-QA/data/train.csv'),qa_selection)
        qa.to_parquet(INTERIM/'qa_vi.parquet',index=False)
        sources = pd.concat([sources,qa],ignore_index=True)
    # Same normalized text always shares a group, including external OOS rows.
    conflict = sources.groupby('group_id').intent.nunique()
    if (conflict > 1).any():
        raise ValueError('Conflicting OOS/Bitext groups; inspect source labels')
    splits = build_splits(sources)
    splits.to_parquet(INTERIM/'splits.parquet',index=False)
    unique,join=translation_input(english)
    unique=unique.merge(splits[['src_id','split']],on='src_id',validate='one_to_one')
    unique.to_parquet(INTERIM/'translation_input.parquet',index=False)
    join.to_parquet(INTERIM/'translation_join.parquet',index=False)


def clean_frame(frame,rng):
    frame=frame.copy()
    frame['text']=[fill_slots(t,rng,lang) for t,lang in zip(frame.text,frame.lang)]
    frame['text']=frame.text.map(normalize_text)
    return frame[frame.text.str.len()>0]


def resolve_conflicts(frames):
    combined=pd.concat(frames,ignore_index=True)
    bad=combined.groupby('text').intent.nunique()
    bad=set(bad[bad>1].index)
    combined[combined.text.isin(bad)].to_csv(REPORT/'conflicting_texts.csv',index=False)
    # Remove cross-split exact duplicates conservatively, retaining evaluation rows.
    cross=combined.groupby('text').split.nunique()
    leakage=set(cross[cross>1].index)
    combined[combined.text.isin(leakage)].to_csv(REPORT/'cross_split_texts.csv',index=False)
    return [f[~f.text.isin(bad|leakage)].drop_duplicates(['text','intent']) for f in frames]


def finalize():
    OUT.mkdir(parents=True,exist_ok=True);REPORT.mkdir(parents=True,exist_ok=True)
    rng=random.Random(42)
    english=pd.read_parquet(INTERIM/'source_en.parquet')
    qc_path=INTERIM/'bitext_vi_qc.parquet'
    qc=json.loads(qc_path.with_suffix('.qc.json').read_text())
    if not qc.get('passed') or qc['sha256']!=hashlib.sha256(qc_path.read_bytes()).hexdigest():
        raise ValueError('Missing, failed or stale translation QC; rerun qc_translation before finalizing')
    vi=pd.read_parquet(qc_path)
    if (INTERIM/'qa_vi.parquet').exists():
        vi=pd.concat([vi,pd.read_parquet(INTERIM/'qa_vi.parquet')],ignore_index=True)
    splits=pd.read_parquet(INTERIM/'splits.parquet')
    frames={}
    for lang,source in [('en',english),('vi',vi)]:
        source=source.drop(columns=['split'],errors='ignore').merge(splits,on=['src_id','group_id'],validate='one_to_one')
        for split in ['train','val','test']:
            rows=[]
            for item in source[source.split==split].sort_values('src_id').to_dict('records'):
                row={k:item.get(k,'') for k in COLUMNS};row['aug_type']='orig';row['lang']=lang
                rows.append(row)
                if split!='train':
                    continue
                if lang=='vi':
                    for _ in range(2):
                        text,kind=augment_vi(row['text'],rng);rows.append({**row,'text':text,'aug_type':kind})
                    paras=item.get('paraphrases')
                    if isinstance(paras,(list,np.ndarray)) and len(paras):
                        rows.append({**row,'text':str(paras[0]),'aug_type':'paraphrase'})
                else:
                    text,kind=augment_en(row['text'],rng)
                    if kind!='orig':rows.append({**row,'text':text,'aug_type':kind})
            key=f'test_clean_{lang}' if split=='test' else f'{split}_{lang}'
            frames[key]=clean_frame(pd.DataFrame(rows,columns=COLUMNS),rng)
    values=resolve_conflicts(list(frames.values()))
    frames=dict(zip(frames,values))
    for lang in ['vi','en']:
        frame=frames[f'train_{lang}']
        # OOS intentionally has fewer examples than Bitext. Balance Bitext intents only.
        scoped=frame[frame.intent!=OOS_LABEL];oos=frame[frame.intent==OOS_LABEL]
        minimum=scoped.intent.value_counts().min();cap=int(minimum*1.5)
        scoped=pd.concat([g.sample(n=min(len(g),cap),random_state=42) for _,g in scoped.groupby('intent')], ignore_index=True)
        frames[f'train_{lang}']=pd.concat([scoped,oos],ignore_index=True)[COLUMNS]
    rng_noisy=random.Random(1234)
    noisy=frames['test_clean_vi'].copy()
    names=list(AUGMENTERS)
    types=(names*((len(noisy)+len(names)-1)//len(names)))[:len(noisy)]
    rng_noisy.shuffle(types)
    noisy['text']=[AUGMENTERS[k](t,rng_noisy) for k,t in zip(types,noisy.text)]
    noisy['aug_type']=types;frames['test_noisy_vi']=noisy
    records=json.loads(Path('data/benchmark_scenarios.json').read_text())
    real=[]
    for i,item in enumerate(records):
        label=item['expected_intent']
        if label=='warranty':label=OOS_LABEL
        if label not in set(ALL_BITEXT_INTENTS)|{OOS_LABEL}:
            raise ValueError(f'Unknown real scenario intent {label}')
        real.append({'src_id':f'real{i:04}','group_id':group_id(item['query']),'text':item['query'],'intent':label,'lang':'vi','aug_type':'orig','split':'test','source':'benchmark'})
    handwritten=pd.read_csv('data/eval/real_vi_handwritten.csv').fillna('')
    if handwritten.empty:
        note='Human-written evaluation CSV is empty; skipped. The team should add 200–300 real queries.'
    else:
        note=f'Included {len(handwritten)} human-written queries.'
        for i,item in handwritten.iterrows():
            if item.intent not in set(ALL_BITEXT_INTENTS)|{OOS_LABEL}:raise ValueError(f'Unknown handwritten intent {item.intent}')
            real.append({'src_id':f'human{i:04}','group_id':group_id(item.text),'text':item.text,'intent':item.intent,'lang':'vi','aug_type':'orig','split':'test','source':'handwritten'})
    frames['test_real']=pd.DataFrame(real,columns=COLUMNS)
    heldout_text=pd.concat([frames[name] for name in ['test_real','test_noisy_vi','test_clean_vi','test_clean_en']],ignore_index=True).text
    real_keys=set(heldout_text.map(lambda t:normalize_text(t).lower()))
    real_groups=set(frames['test_real'].group_id)
    for key in ['train_vi','train_en','val_vi','val_en']:
        f=frames[key]
        frames[key]=f[~f.group_id.isin(real_groups)&~f.text.map(lambda t:normalize_text(t).lower()).isin(real_keys)]
    frames['train_multi']=pd.concat([frames['train_vi'],frames['train_en']],ignore_index=True)
    no_tone=frames['test_clean_vi'].copy();no_tone['text']=no_tone.text.map(no_diacritic);no_tone['aug_type']='no_diacritic'
    frames['router_eval']=pd.concat([frames['test_clean_en'],frames['test_clean_vi'],no_tone],ignore_index=True)
    base=pd.concat([frames[k] for k in ['train_en','train_vi','val_en','val_vi','test_clean_en','test_clean_vi']],ignore_index=True)
    assert base.groupby('group_id').split.nunique().max()==1,'group leakage'
    assert base.groupby('src_id').split.nunique().max()==1,'source leakage'
    for name,frame in frames.items():
        if frame.empty:raise ValueError(f'{name} is empty after QC/deduplication')
        frame[COLUMNS].sort_values(['src_id','aug_type','text'],kind='stable').reset_index(drop=True).to_parquet(OUT/f'{name}.parquet',index=False)
    summary=pd.concat([frame.assign(dataset=name) for name,frame in frames.items()],ignore_index=True).groupby(['dataset','split','lang','intent','aug_type']).size().rename('count').reset_index()
    summary.to_csv(REPORT/'data_summary.csv',index=False)
    (REPORT/'data_summary.md').write_text('# Module 1 data\n\n'+note+'\n\nSeed: 42; noisy seed: 1234. OOS is excluded from Bitext balance cap.\n\n```csv\n'+summary.to_csv(index=False)+'```\n')
    print(summary.to_string(index=False))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('stage',choices=['prepare','qc-pairs','finalize','inspect-qa'])
    parser.add_argument('--translated',type=Path,default=Path('kaggle/output/k01/bitext_vi_translated.parquet'))
    parser.add_argument('--qa-selection',type=Path,help='JSON: reviewed non-commerce type -> reason')
    args=parser.parse_args()
    if args.stage=='prepare':prepare(json.loads(args.qa_selection.read_text()) if args.qa_selection else None)
    elif args.stage=='qc-pairs':
        pairs=prepare_pairs(pd.read_parquet(INTERIM/'source_en.parquet'),pd.read_parquet(args.translated),pd.read_parquet(INTERIM/'translation_join.parquet'))
        pairs.to_parquet(INTERIM/'qc_pairs.parquet',index=False)
    elif args.stage=='inspect-qa':inspect_qa(Path('data/raw/Vietnamese-Customer-Support-QA/data/train.csv'))
    else:finalize()


if __name__=='__main__':main()
