"""A2: fit LR locally and evaluate the exact ONNX serving path on held-out data."""
import argparse
import shutil
import time
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from services.intent_service.src.predictor import MiniLMLRBackend
from services.intent_service.src.preprocessing import preprocess
from services.intent_service.src.pipeline.experiments.common import DATA,make_run_id,record_run,write_meta


class ServingAdapter:
    def __init__(self,backend,classes):self.backend=backend;self.classes_=np.asarray(classes)
    def predict_proba(self,texts):
        return np.stack([self.backend.predict_proba(preprocess(t)) for t in texts])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--embeddings',type=Path,required=True);args=parser.parse_args()
    start=time.perf_counter();frames={};embeddings={}
    for name in ['train_multi','val_vi','val_en','test_clean_vi','test_noisy_vi','test_real','test_clean_en']:
        frame=pd.read_parquet(DATA/f'{name}.parquet');ids=pd.read_parquet(args.embeddings/f'ids_{name}.parquet')
        if not frame[['src_id','text','aug_type']].reset_index(drop=True).equals(ids[['src_id','text','aug_type']].reset_index(drop=True)):
            raise ValueError(f'Embedding row alignment mismatch for {name}')
        array=np.load(args.embeddings/f'emb_{name}.npy').astype(np.float32)
        if len(array)!=len(frame):raise ValueError('Embedding length mismatch')
        frames[name]=frame;embeddings[name]=array
    vx=np.concatenate([embeddings['val_vi'],embeddings['val_en']]);val=pd.concat([frames['val_vi'],frames['val_en']],ignore_index=True)
    best=None;score=-1
    for c in [1,5,10]:
        model=LogisticRegression(C=c,max_iter=3000,random_state=42).fit(embeddings['train_multi'],frames['train_multi'].intent)
        f1=f1_score(val.intent,model.predict(vx),average='macro')
        if f1>score:best=model;score=f1
    train_time=time.perf_counter()-start
    for filename,tag in [('model.onnx','fp32'),('model_int8.onnx','int8')]:
        method='A2-minilm-lr-'+tag
        artifact=Path('artifacts/models/intent/runs')/make_run_id(method,'multi');artifact.mkdir(parents=True)
        joblib.dump(best,artifact/'lr.joblib')
        shutil.copytree(args.embeddings/'minilm_onnx',artifact,dirs_exist_ok=True)
        write_meta(artifact,method,'multi',best.classes_,None,backend='minilm_lr',model_file=filename,max_length=128)
        import json
        meta=json.loads((artifact/'meta.json').read_text())
        adapter=ServingAdapter(MiniLMLRBackend(artifact,meta),best.classes_)
        tests={name:f for name,f in frames.items() if name.startswith('test_')}
        for name,test in tests.items():
            reference=f1_score(test.intent,best.predict(embeddings[name]),average='macro')
            actual=f1_score(test.intent,best.classes_[adapter.predict_proba(test.text).argmax(axis=1)],average='macro')
            if reference-actual>.01:raise ValueError(f'MiniLM {tag} Macro-F1 drops more than one point on {name}; inspect export/pooling before deployment')
        record_run(adapter,artifact,method,'multi',len(frames['train_multi']),train_time,val,tests,
            raw_validation_probs=best.predict_proba(vx),extra={'meta':{'backend':'minilm_lr','model_file':filename,'max_length':128}})


if __name__=='__main__':main()
