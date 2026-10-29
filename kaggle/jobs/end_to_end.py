"""One-session Kaggle pipeline: Bitext EN -> Vietnamese -> group split -> VI/EN train/eval.

All translations are created before any source row is assigned a split. A run writes
its full data, calibration, reports, latency measurements and inference bundle to
/kaggle/working/module1-output. No output or benchmark number is committed to Git.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('TOKENIZERS_PARALLELISM','false')
import hashlib
import json
import random
import re
import subprocess
import time
import unicodedata
import warnings
from pathlib import Path

SEED=42
random.seed(SEED)
import numpy as np
np.random.seed(SEED)
import pandas as pd
import torch
torch.manual_seed(SEED)
torch.cuda.manual_seed_all(SEED)

ROOT=Path('/kaggle/working/E-commerce-Support-Copilot')
import sys
if ROOT.exists():sys.path.insert(0,str(ROOT))
from services.intent_service.src.preprocessing import preprocess
OUT=Path('/kaggle/working/module1-output')
OUT.mkdir(parents=True,exist_ok=True)
DATA=OUT/'data'
DATA.mkdir(exist_ok=True)
START=time.monotonic()

INTENTS=sorted('''add_product availability availability_in_store availability_online cancel_order change_account change_order close_account customer_service damaged_delivery delivery_issue delivery_time exchange_product exchange_product_in_store human_agent missing_item open_account order_history pay payment_issue payment_methods product_information product_issue recover_password refund_policy refund_status remove_product request_invoice request_refund request_right_to_rectification return_policy return_product return_product_in_store return_product_online sales_period shipping_costs store_location store_opening_hours submit_feedback submit_product_feedback submit_product_idea technical_issue track_delivery track_order use_app wrong_item'''.split())
TARGET_INTENTS=set('track_order cancel_order delivery_time delivery_issue shipping_costs return_policy return_product refund_policy request_refund refund_status payment_issue human_agent'.split())
SLOT=re.compile(r'\{\{[^}]+\}\}')


def log(message):print(f'[{time.strftime("%H:%M:%S")}] {message}',flush=True)


def save_json(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False))


def normalize(text):return re.sub(r'\s+',' ',unicodedata.normalize('NFC',str(text))).strip()


def norm_key(text):
    protected=SLOT.sub(' <slot> ',preprocess(text))
    return re.sub(r'\s+',' ',re.sub(r'[^\w\s<>]',' ',protected)).strip()


def remove_diacritics(text):
    return ''.join(ch for ch in unicodedata.normalize('NFD',text) if not unicodedata.combining(ch)).replace('đ','d').replace('Đ','D')


def protect(text):
    mapping={}
    def sub(match):
        token=f'[[SLOT{len(mapping)}]]';mapping[token]=match.group(0);return token
    return SLOT.sub(sub,text),mapping


def restore(text,mapping):
    lost=any(text.count(token)!=1 for token in mapping) or set(re.findall(r'\[\[SLOT\d+\]\]',text))!=set(mapping)
    for token,value in mapping.items():text=text.replace(token,value)
    return normalize(text),lost


def order_value(rng):return f'ORD-{rng.randint(1000,999999)}'


def fill_slots(text,lang,rng):
    values={'Order Number':lambda:order_value(rng),'Order ID':lambda:order_value(rng),
            'Person Name':lambda:rng.choice(['Nguyễn An','Trần Minh','Lê Hà'] if lang=='vi' else ['Alex Smith','Jamie Brown','Sam Lee']),
            'Product Name':lambda:rng.choice(['áo thun','tai nghe','giày'] if lang=='vi' else ['shirt','headphones','shoes']),
            'Email Address':lambda:f'customer{rng.randrange(10000)}@example.com',
            'Email':lambda:f'customer{rng.randrange(10000)}@example.com',
            'Amount':lambda:f'{rng.randrange(10,1000)} VND' if lang=='vi' else f'{rng.randrange(10,1000)} USD',
            'Date':lambda:'2026-05-14','Time':lambda:'14:30','Phone Number':lambda:'0901234567',
            'Store Name':lambda:'Demo Store','Website URL':lambda:'https://example.com'}
    def sub(match):
        key=match.group(0)[2:-2].strip()
        factory=next((v for k,v in values.items() if k.lower()==key.lower()),None)
        return factory() if factory else key
    return normalize(SLOT.sub(sub,text))


def translate_all(source):
    """GPU translation, checkpointed every 1000 rows; translation precedes split."""
    from transformers import AutoTokenizer,AutoModelForSeq2SeqLM
    if not torch.cuda.is_available():raise RuntimeError('Kaggle GPU is required; enable GPU in notebook settings')
    checkpoint=DATA/'translation_checkpoint.parquet'
    source=source.to_dict('records') if isinstance(source,pd.DataFrame) else list(source)
    done=pd.read_parquet(checkpoint).to_dict('records') if checkpoint.exists() else []
    translated={r['src_id']:r for r in done}
    pending=[row for row in source if row['src_id'] not in translated]
    model_name='vinai/vinai-translate-en2vi-v2';nllb=False
    try:
        tok=AutoTokenizer.from_pretrained(model_name,src_lang='en_XX')
        model=AutoModelForSeq2SeqLM.from_pretrained(model_name).half().cuda().eval()
    except Exception as exc:
        log(f'Primary translation model load failed ({exc}); trying NLLB fallback')
        model_name='facebook/nllb-200-distilled-600M';nllb=True
        tok=AutoTokenizer.from_pretrained(model_name,src_lang='eng_Latn')
        model=AutoModelForSeq2SeqLM.from_pretrained(model_name).half().cuda().eval()
    target='vie_Latn' if nllb else 'vi_VN'
    target_id=tok.lang_code_to_id[target] if hasattr(tok,'lang_code_to_id') else tok.convert_tokens_to_ids(target)
    if target_id is None or target_id==tok.unk_token_id:raise ValueError(f'Translator has no target language token {target}')
    pending.sort(key=lambda row:len(row['protected']))
    for offset in range(0,len(pending),32):
        batch=pending[offset:offset+32]
        encoded=tok([r['protected'] for r in batch],return_tensors='pt',padding=True,truncation=True,max_length=128).to('cuda')
        args={'forced_bos_token_id':target_id} if nllb else {'decoder_start_token_id':target_id}
        with torch.inference_mode():generated=model.generate(**encoded,**args,num_beams=4,early_stopping=True,max_new_tokens=128)
        for row,raw in zip(batch,tok.batch_decode(generated,skip_special_tokens=True)):
            slots=row['slots'] if isinstance(row['slots'],dict) else json.loads(row['slots'])
            vi,lost=restore(raw,slots)
            translated[row['src_id']]={**row,'text_vi':vi,'slot_lost':bool(lost),'translator':model_name}
        if (offset//32+1)%31==0 or offset+48>=len(pending):
            done=list(translated.values());pd.DataFrame(done).to_parquet(checkpoint,index=False)
            log(f'Translated {len(done)}/{len(source)} unique utterances')
    table=pd.DataFrame(translated.values())
    requested={row['src_id'] for row in source}
    missing=requested-set(table.src_id)
    if missing:raise ValueError(f'Translation row mismatch: {len(missing)} requested source IDs are missing')
    table.to_parquet(DATA/'bitext_vi_translated.parquet',index=False)
    lost=int(table.slot_lost.sum());ratio=lost/max(1,len(table))
    save_json(OUT/'translation_metrics.json',{'unique_rows':len(table),'slot_lost':lost,'slot_lost_rate':ratio,'translator':model_name,'elapsed_minutes':round((time.monotonic()-START)/60,2)})
    sample=table.sample(n=min(20,len(table)),random_state=SEED)[['text_en','text_vi','slot_lost','intent']]
    sample.to_csv(OUT/'translation_samples.csv',index=False)
    log(f'Translation sample (EN → VI):\n{sample.head(10).to_string(index=False)}')
    if ratio>=.05:raise RuntimeError(f'{ratio:.2%} of rows lost placeholders (limit 5%). Translation is saved for inspection; training stopped.')
    return table[table.src_id.isin(requested)].reset_index(drop=True)


def load_source_data():
    """Download actual Bitext/CLINC data; no generated fake query is treated as evaluation."""
    from datasets import load_dataset
    cache=DATA/'source.parquet'
    if cache.exists():return pd.read_parquet(cache)
    dataset=load_dataset('bitext/Bitext-retail-ecommerce-llm-chatbot-training-dataset',split='train')
    source=dataset.select_columns(['instruction','intent','category','tags']).to_pandas()
    if len(source)!=44884 or set(source.intent)!=set(INTENTS):
        raise ValueError(f'Unexpected Bitext source: rows={len(source)}, labels={sorted(set(source.intent))}')
    rows=[]
    for index,row in source.iterrows():
        text=normalize(row.instruction);protected,mapping=protect(text)
        raw_slots=json.dumps(mapping,ensure_ascii=False)
        src='b'+str(index).zfill(6); group=hashlib.sha256(norm_key(text).encode()).hexdigest()[:20]
        rows.append({'src_id':src,'group_id':group,'text_en':text,'protected':protected,'slots':raw_slots,'intent':row.intent,'category':row.category,'tags':row.tags,'lang':'en','source':'bitext'})
    # Keep one translation per exact protected sentence; restore label/source rows after translating.
    frame=pd.DataFrame(rows)
    duplicates=frame.drop_duplicates('protected').copy()
    duplicates.to_parquet(DATA/'translation_unique.parquet',index=False)
    frame.to_parquet(DATA/'source_rows.parquet',index=False)
    # Source cache records the complete unique translation requests only.
    duplicates.to_parquet(cache,index=False)
    return duplicates


def add_oos(source):
    """Add real out-of-domain CLINC examples, translated with their English source."""
    from datasets import load_dataset
    clinc=load_dataset('clinc_oos','plus')
    rows=[];seen=set()
    for split in clinc.values():
        names=split.features['intent'].names
        for row in split:
            if names[row['intent']]=='oos' and row['text'] not in seen:
                seen.add(row['text']);rows.append(normalize(row['text']))
    rows=sorted(rows)
    rng=random.Random(SEED);rng.shuffle(rows);rows=rows[:1200]
    base=[]
    for i,text in enumerate(rows):
        protected,mapping=protect(text);sid='oos'+hashlib.sha256(text.encode()).hexdigest()[:16]
        base.append({'src_id':sid,'group_id':hashlib.sha256(('oos'+norm_key(text)).encode()).hexdigest()[:20], 'text_en':text,'protected':protected,'slots':json.dumps(mapping),'intent':'out_of_scope','category':'OOS','tags':'','lang':'en','source':'clinc_oos'})
    out=pd.DataFrame(base);out.to_parquet(DATA/'clinc_oos_source.parquet',index=False)
    return pd.concat([source,out],ignore_index=True)


def split_sources(frame):
    from sklearn.model_selection import StratifiedGroupKFold
    # Groups are stable English source IDs, so EN and translated VI siblings share a split.
    source=frame.drop_duplicates('src_id').reset_index(drop=True)
    splitter=StratifiedGroupKFold(n_splits=10,shuffle=True,random_state=SEED)
    assignment=np.full(len(source),'train',dtype=object)
    for fold,(_,indices) in enumerate(splitter.split(source,source.intent,source.group_id)):
        if fold==0:assignment[indices]='test'
        elif fold==1:assignment[indices]='val'
    source['split']=assignment
    assert source.groupby('group_id').split.nunique().max()==1
    return source[['src_id','split']]


def augment_vi(text,rng):
    return remove_diacritics(text) if rng.random()<.70 else ' '.join(remove_diacritics(w) if rng.random()<.5 else w for w in text.split())


def make_frames(source):
    rng=random.Random(SEED)
    joined=source.copy()
    if joined.text_vi.isna().any():raise ValueError('One or more source rows did not receive a translation')
    splits=split_sources(joined)
    joined=joined.merge(splits,on='src_id',validate='one_to_one')
    frames={}
    for lang,col in [('en','text_en'),('vi','text_vi')]:
        clean=joined.copy()
        clean['text']=[fill_slots(t,lang,rng) for t in clean[col]]
        if lang=='vi':clean=clean[~clean.slot_lost]
        for split in ['train','val','test']:
            rows=[]
            subset=clean[clean.split==split]
            for row in subset.to_dict('records'):
                base={'src_id':row['src_id'],'group_id':row['group_id'],'text':row['text'],'intent':row['intent'],'lang':lang,'aug_type':'orig','split':split,'source':row['source']}
                rows.append(base)
                if split=='train' and lang=='vi':
                    rows.append({**base,'text':augment_vi(base['text'],rng),'aug_type':'diacritic_noise'})
                elif split=='train' and lang=='en' and rng.random()<.3:
                    rows.append({**base,'text':base['text'].lower(),'aug_type':'lowercase'})
            key=f'train_{lang}' if split=='train' else f'val_{lang}' if split=='val' else f'test_clean_{lang}'
            frame=pd.DataFrame(rows)
            conflicts=frame.groupby('text').intent.nunique();bad=set(conflicts[conflicts>1].index)
            frame=frame[~frame.text.isin(bad)].drop_duplicates(['text','intent']).reset_index(drop=True)
            frames[key]=frame
    frames['test_nodiac_vi']=frames['test_clean_vi'].copy()
    frames['test_nodiac_vi']['text']=frames['test_nodiac_vi'].text.map(remove_diacritics)
    frames['test_nodiac_vi']['aug_type']='no_diacritic'
    scenarios=json.loads((ROOT/'data/benchmark_scenarios.json').read_text(encoding='utf-8-sig'))
    real=[];excluded=0
    for i,row in enumerate(scenarios):
        intent=row['expected_intent']
        if intent not in INTENTS:excluded+=1;continue
        q=normalize(row['query']);sid='real'+str(i).zfill(4)
        real.append({'src_id':sid,'group_id':hashlib.sha256(('real'+norm_key(q)).encode()).hexdigest()[:20],'text':fill_slots(q,'vi',rng),'intent':intent,'lang':'vi','aug_type':'orig','split':'test','source':'benchmark'})
    frames['test_real']=pd.DataFrame(real)
    # Benchmark scenarios are held out from training/validation if their source text matches.
    test_groups=set(frames['test_real'].group_id) if real else set()
    test_texts=set(frames['test_real'].text.map(norm_key)) if real else set()
    for key in ['train_vi','train_en','val_vi','val_en']:
        frames[key]=frames[key][~frames[key].group_id.isin(test_groups)&~frames[key].text.map(norm_key).isin(test_texts)]
    save_json(OUT/'data_summary.json',{'rows':{k:len(v) for k,v in frames.items()},'intents':INTENTS,'benchmark_rows_excluded':excluded,'seed':SEED,'translation_before_split':True})
    for name,frame in frames.items():frame.to_parquet(DATA/f'{name}.parquet',index=False)
    return frames


def make_pipeline(kind,c):
    from sklearn.pipeline import Pipeline,FeatureUnion
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.svm import LinearSVC
    features=FeatureUnion([('word',TfidfVectorizer(preprocessor=preprocess,ngram_range=(1,2),sublinear_tf=True,min_df=2)),('char',TfidfVectorizer(preprocessor=preprocess,analyzer='char_wb',ngram_range=(2,5),sublinear_tf=True,min_df=2,max_features=200000))])
    estimator=LogisticRegression(C=c,max_iter=2000,class_weight='balanced',random_state=SEED) if kind=='lr' else LinearSVC(C=c,class_weight='balanced',random_state=SEED)
    return Pipeline([('features',features),('classifier',estimator)])


def calibrate_svc(pipe,train):
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.model_selection import StratifiedGroupKFold
    # Features are fit per fold to avoid calibration leakage.
    splits=list(StratifiedGroupKFold(n_splits=3,shuffle=True,random_state=SEED).split(train.text,train.intent,train.group_id))
    return CalibratedClassifierCV(pipe,method='sigmoid',cv=splits,n_jobs=1)


def ece(y,probs,classes,bins=15):
    conf=probs.max(axis=1);pred=np.asarray(classes)[probs.argmax(axis=1)];y=np.asarray(y);total=0.
    for i in range(bins):
        mask=(conf>=i/bins)&((conf<(i+1)/bins) if i<bins-1 else (conf<=1))
        if mask.any():total+=mask.mean()*abs(np.mean(pred[mask]==y[mask])-conf[mask].mean())
    return float(total)


def threshold_for(y,probs,classes):
    conf=probs.max(axis=1);pred=np.asarray(classes)[probs.argmax(axis=1)]
    for threshold in np.round(np.arange(.30,.951,.01),2):
        keep=conf>=threshold
        if keep.any() and np.mean(pred[keep]==np.asarray(y)[keep])>=.95:return float(threshold),float(keep.mean())
    return None,0.


def score_test(model,frame,classes):
    from sklearn.metrics import accuracy_score,f1_score,classification_report,confusion_matrix
    probs=model.predict_proba(frame.text);pred=np.asarray(classes)[probs.argmax(axis=1)]
    report=classification_report(frame.intent,pred,labels=list(classes),output_dict=True,zero_division=0)
    per=[{'intent':label,'precision':report[label]['precision'],'recall':report[label]['recall'],'f1':report[label]['f1-score'],'support':report[label]['support']} for label in classes]
    matrix=confusion_matrix(frame.intent,pred,labels=list(classes))
    pairs=sorted([{'true':a,'pred':b,'count':int(matrix[i,j])} for i,a in enumerate(classes) for j,b in enumerate(classes) if i!=j and matrix[i,j]],key=lambda r:r['count'],reverse=True)[:20]
    return probs,{'macro_f1':float(f1_score(frame.intent,pred,average='macro',zero_division=0)),'accuracy':float(accuracy_score(frame.intent,pred)),'ece':ece(frame.intent,probs,classes)},pd.DataFrame(per),pd.DataFrame(pairs,columns=['true','pred','count'])


def train_and_evaluate(frames):
    from sklearn.metrics import f1_score
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.base import clone
    from threadpoolctl import threadpool_limits
    import joblib
    results=[];models={};model_root=OUT/'artifacts/models/intent';model_root.mkdir(parents=True,exist_ok=True)
    candidates=[('lr',c) for c in [1,5,10,20]]+[('svc',c) for c in [.1,.5,1.]]
    for lang in ['vi','en']:
        log(f'Training B1 {lang.upper()} on Kaggle CPU')
        train=frames[f'train_{lang}'];val=frames[f'val_{lang}']
        if train.empty or val.empty:raise ValueError(f'Empty train/validation frame for {lang}')
        grid=[];best=None;best_f1=-1
        for kind,c in candidates:
            start=time.perf_counter();pipe=make_pipeline(kind,c)
            if kind=='svc':model=calibrate_svc(pipe,train)
            else:model=pipe
            model.fit(train.text,train.intent)
            val_pred=model.predict(val.text);macro=float(f1_score(val.intent,val_pred,average='macro',zero_division=0))
            grid.append({'method':kind,'C':c,'validation_macro_f1':macro,'fit_seconds':time.perf_counter()-start})
            if macro>best_f1:best,best_f1,chosen=(model,macro,(kind,c))
            log(f'{lang} {kind} C={c}: val macro-F1={macro:.4f}')
        pd.DataFrame(grid).to_csv(OUT/f'grid_{lang}.csv',index=False)
        classes=list(map(str,best.classes_));val_probs=best.predict_proba(val.text);threshold,coverage=threshold_for(val.intent,val_probs,classes)
        lang_tests=['test_clean_'+lang]
        if lang=='vi':lang_tests+=['test_nodiac_vi','test_real']
        metrics={};per_by_test={};pairs_by_test={}
        for test_name in lang_tests:
            test=frames[test_name]
            if test.empty:continue
            probs,score,per,pairs=score_test(best,test,classes);metrics[test_name]=score
            per.to_csv(OUT/f'per_intent_f1_{lang}_{test_name}.csv',index=False)
            pairs.to_csv(OUT/f'confusion_top20_{lang}_{test_name}.csv',index=False)
            per_by_test[test_name]=per.to_dict('records');pairs_by_test[test_name]=pairs.to_dict('records')
        # End-to-end local CPU latency measured in this Kaggle kernel. Results record
        # the actual Kaggle hardware so they are not represented as local-machine SLA.
        corpus=pd.concat([frames.get('test_clean_vi',pd.DataFrame()),frames.get('test_nodiac_vi',pd.DataFrame()),frames.get('test_clean_en',pd.DataFrame())],ignore_index=True)
        sample=corpus.sample(n=min(500,len(corpus)),random_state=SEED)
        latency=[]
        with threadpool_limits(limits=1):
            for text in sample.text.iloc[:50]:best.predict_proba([preprocess(text)])
            for text in sample.text:
                start=time.perf_counter();best.predict_proba([preprocess(text)]);latency.append((time.perf_counter()-start)*1000)
        lat={'mean_ms':float(np.mean(latency)),'p50_ms':float(np.percentile(latency,50)),'p95_ms':float(np.percentile(latency,95)),'p99_ms':float(np.percentile(latency,99)),'mode':'single-thread batch=1; intent backend only; measured in Kaggle CPU'}
        artifact=model_root/lang;artifact.mkdir(parents=True,exist_ok=True);joblib.dump(best,artifact/'model.joblib')
        meta={'backend':'sklearn','method':f'tfidf-{chosen[0]}','lang':lang,'classes':classes,'threshold':threshold,'coverage':coverage,'ece':ece(val.intent,val_probs,classes),'library_versions':{'scikit-learn':__import__('sklearn').__version__},'trained_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'metrics':metrics,'latency_ms':lat}
        save_json(artifact/'meta.json',meta);models[lang]=best
        report_set='test_nodiac_vi' if lang=='vi' else 'test_clean_en'
        results.append({'lang':lang,'method':meta['method'],'threshold':threshold,'coverage':coverage,'ece':meta['ece'],'latency_ms':lat,'tests':metrics,'grid':grid,'per_intent':per_by_test.get(report_set,[]),'confusions':pairs_by_test.get(report_set,[])})
    return results,models


def fit_router(frames):
    from collections import Counter
    from sklearn.metrics import accuracy_score,confusion_matrix
    english=set(re.findall(r'[a-z]+',' '.join(frames['train_en'].text).lower()))
    tokens=Counter(re.findall(r'[a-z]+',' '.join(remove_diacritics(t) for t in frames['train_vi'].text).lower()))
    vocab=[t for t,_ in tokens.most_common() if t not in english][:300]
    val_en=frames['val_en'];val_vi=frames['val_vi'].copy();val_vi['text']=val_vi.text.map(remove_diacritics)
    val=pd.concat([val_en.assign(lang='en'),val_vi.assign(lang='vi')],ignore_index=True)
    token_re=re.compile(r'[a-z]+')
    def score(text,threshold):
        if re.search(r'[ăâđêôơưàáạảãằắặẳẵầấậẩẫèéẹẻẽềếệểễìíịỉĩòóọỏõồốộổỗờớợởỡùúụủũừứựửữỳýỵỷỹ]',text,re.I):return 'vi'
        words=token_re.findall(text.lower())
        return 'vi' if words and sum(w in vocab_set for w in words)/len(words)>=threshold else 'en'
    vocab_set=set(vocab);best=(0,.2)
    for t in np.round(np.arange(.1,.601,.05),2):
        accuracy=accuracy_score(val.lang,[score(text,t) for text in val.text])
        if accuracy>best[0]:best=(accuracy,float(t))
    threshold=best[1]
    model_root=OUT/'artifacts/models/intent/router';model_root.mkdir(parents=True,exist_ok=True)
    (model_root/'vi_notone.txt').write_text('\n'.join(vocab)+'\n')
    save_json(model_root/'meta.json',{'threshold':threshold,'seed':SEED})
    test=pd.concat([frames['test_clean_en'].assign(lang='en'),frames['test_clean_vi'].assign(lang='vi'),frames['test_nodiac_vi'].assign(lang='vi')],ignore_index=True)
    pred=[score(text,threshold) for text in test.text];accuracy=float(accuracy_score(test.lang,pred))
    nodiac=frames['test_nodiac_vi'];nodiac_accuracy=float(accuracy_score(['vi']*len(nodiac),[score(text,threshold) for text in nodiac.text]))
    report={'validation_accuracy':best[0],'test_accuracy':accuracy,'test_nodiac_vi_accuracy':nodiac_accuracy,'threshold':threshold,'confusion_en_vi':confusion_matrix(test.lang,pred,labels=['en','vi']).tolist(),'vocabulary_size':len(vocab)}
    save_json(OUT/'router_metrics.json',report)
    return report


def main():
    log('Cloning branch hung; installing runtime modules from repository')
    clone_url='https://github.com/DunnTapCodee/E-commerce-Support-Copilot.git'
    if not ROOT.exists():subprocess.run(['git','clone','--depth','1','--branch','hung',clone_url,str(ROOT)],check=True)
    import sklearn
    if sklearn.__version__!='1.6.1':raise RuntimeError(f'Install scikit-learn==1.6.1 before running; got {sklearn.__version__}')
    source=load_source_data()
    log(f'Bitext: {len(source)} unique source queries from 44,884 labelled rows')
    # The expensive machine translation is done for each unique instruction first;
    # source siblings are rejoined before group split so translations cannot leak.
    translated=translate_all(source)
    if len(translated)!=len(source):raise ValueError('Translation count differs from source rows')
    source_rows=pd.read_parquet(DATA/'source_rows.parquet')
    # Map each raw row to exactly one translation, including duplicate instructions.
    map_cols=source[['src_id','text_en','intent','category','tags','source']].merge(translated[['src_id','text_vi','slot_lost','group_id']],on='src_id',validate='one_to_one')
    # Translation cache is unique-text based; reconstruct all labeled rows by protected text.
    unique_translation=translated.drop_duplicates('protected').set_index('protected')
    if len(source_rows):
        # Retain source ids/labels from original Bitext and attach their shared translation.
        source_rows['translation_key']=source_rows.protected
        translation_lookup=translated.drop_duplicates('protected').set_index('protected')
        source_rows['text_vi']=source_rows.translation_key.map(translation_lookup.text_vi)
        source_rows['slot_lost']=source_rows.translation_key.map(translation_lookup.slot_lost).fillna(True).astype(bool)
        source_rows['group_id']=source_rows.text_en.map(lambda t:hashlib.sha256(norm_key(t).encode()).hexdigest()[:20])
        source_rows['source']='bitext'
        source_rows['lang']='en'
    else:source_rows=map_cols
    # Generate/translate genuine English OOS examples and append both languages.
    oos=add_oos(pd.DataFrame(columns=source_rows.columns))
    # add_oos creates an EN translation source table; translate its OOS rows before combining.
    oos['slots']=oos.get('slots',pd.Series(['{}']*len(oos))).fillna('{}')
    if len(oos):
        # Reuse a deterministic translation checkpoint if present.
        translated_oos=translate_all(oos)
        oos['text_vi']=oos.src_id.map(translated_oos.set_index('src_id').text_vi)
        oos['slot_lost']=oos.src_id.map(translated_oos.set_index('src_id').slot_lost).fillna(True).astype(bool)
    all_rows=pd.concat([source_rows,oos],ignore_index=True)
    save_json(OUT/'dataset_source_metrics.json',{'bitext_source_rows':len(source_rows),'unique_translations':len(translated),'clinc_oos_rows':len(oos),'translated_before_split':True})
    # Translate external OOS first too, then apply a single group-safe split to all sources.
    frames=make_frames(all_rows)
    log('Language router and B1 VI/EN model evaluation started')
    router=fit_router(frames)
    results,models=train_and_evaluate(frames)
    valid_thresholds=[r['threshold'] for r in results if r['threshold'] is not None]
    recommended_threshold=min(valid_thresholds) if len(valid_thresholds)==2 else None
    save_json(OUT/'metrics.json',{'results':results,'router':router,'recommended_gateway_threshold':recommended_threshold,'data':json.loads((OUT/'data_summary.json').read_text()),'translation':json.loads((OUT/'translation_metrics.json').read_text())})
    summary=['# Module 1 — end-to-end Kaggle run','',f'Run date UTC: {time.strftime("%Y-%m-%d %H:%M:%S",time.gmtime())}','',f'Kaggle device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"}','',f'VI/EN router test accuracy: {router["test_accuracy"]:.4f}; VI no-diacritic: {router["test_nodiac_vi_accuracy"]:.4f}',f'Recommended shared gateway threshold (minimum of VI/EN validation cutoffs): {recommended_threshold}','']
    for item in results:
        summary += [f'## {item["lang"].upper()} — {item["method"]}','',f'Confidence cutoff: {item["threshold"]}; coverage: {item["coverage"]:.4f}; ECE: {item["ece"]:.4f}; p95: {item["latency_ms"]["p95_ms"]:.3f} ms','', '| Test set | Macro-F1 | Accuracy | ECE |','|---|---:|---:|---:|']
        summary += [f'| {name} | {score["macro_f1"]:.4f} | {score["accuracy"]:.4f} | {score["ece"]:.4f} |' for name,score in item['tests'].items()]
        weakest=sorted(item['per_intent'],key=lambda r:r['f1'])[:10]
        summary += ['', 'Weakest intent F1:', '', '| Intent | F1 | Support |','|---|---:|---:|']
        summary += [f'| {row["intent"]} | {row["f1"]:.4f} | {row["support"]} |' for row in weakest]
        summary += ['', 'Top confusion pairs:']
        summary += [f'- {row["true"]} → {row["pred"]}: {row["count"]}' for row in sorted(item['confusions'],key=lambda r:r['count'],reverse=True)[:10]]
        summary.append('')
    (OUT/'RESULTS.md').write_text('\n'.join(summary)+'\n')
    import shutil
    shutil.make_archive(str(OUT/'intent_bundle'),'zip',root_dir=OUT/'artifacts/models/intent')
    log(f'COMPLETE. Results and inference artifacts: {OUT}')
    log('Download Kaggle output: RESULTS.md, metrics.json, data/, artifacts/models/intent/, intent_bundle.zip')


if __name__=='__main__':main()
