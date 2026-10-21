"""Validate downloaded ONNX fp32/int8 artifacts on local CPU, then register runs."""
import argparse
import json
import shutil
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score
from scipy.special import softmax
from services.intent_service.src.predictor import OnnxTransformerBackend
from services.intent_service.src.preprocessing import preprocess
from services.intent_service.src.pipeline.experiments.common import DATA,RESULTS,make_run_id,record_run


class OnnxAdapter:
    def __init__(self,backend,classes):self.backend=backend;self.classes_=np.asarray(classes)
    def predict_proba(self,texts):return np.stack([self.backend.predict_proba(preprocess(t)) for t in texts])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);args=parser.parse_args()
    meta=json.loads((args.source/'meta.json').read_text());lang=meta['lang'];method=meta['method']
    val=pd.read_parquet(DATA/f'val_{lang}.parquet')
    tests={name:pd.read_parquet(DATA/f'{name}.parquet') for name in (['test_clean_vi','test_noisy_vi','test_real'] if lang=='vi' else ['test_clean_en'])}
    original=json.loads((args.source/'metrics_kaggle.json').read_text())
    val_ids=pd.read_parquet(args.source/'ids_val.parquet')
    if not val[['src_id','text','intent','aug_type']].reset_index(drop=True).equals(val_ids.reset_index(drop=True)):
        raise ValueError('Local/Kaggle validation rows differ')
    for filename,tag in [('model.onnx','fp32'),('model_int8.onnx','int8')]:
        artifact=Path('artifacts/models/intent/runs')/make_run_id(method+'-'+tag,lang);artifact.mkdir(parents=True)
        shutil.copytree(args.source/'onnx',artifact,dirs_exist_ok=True)
        config={**meta,'model_file':filename};(artifact/'meta.json').write_text(json.dumps(config))
        backend=OnnxTransformerBackend(artifact,config);adapter=OnnxAdapter(backend,meta['classes'])
        # Reject mismatched local test files, rather than compare different populations.
        for name,frame in tests.items():
            ids=pd.read_parquet(args.source/f'ids_{name}.parquet')
            if not frame[['src_id','text','intent','aug_type']].reset_index(drop=True).equals(ids.reset_index(drop=True)):
                raise ValueError(f'Local/Kaggle evaluation rows differ for {name}')
            local=f1_score(frame.intent,np.asarray(meta['classes'])[adapter.predict_proba(frame.text).argmax(axis=1)],average='macro')
            if original['tests'][name]['macro_f1']-local>.01:
                raise ValueError(f'{tag} Macro-F1 drops by more than one point on {name}; do not deploy')
        record_run(adapter,artifact,method+'-'+tag,lang,original['train_size'],original.get('train_time_s',0),val,tests,
            raw_validation_probs=softmax(np.load(args.source/'logits_val.npy'),axis=1),
            extra={'transformers_version':meta['library_versions']['transformers'],'meta':{**{k:config[k] for k in ['backend','model_file','max_length','temperature','needs_word_segmentation']},'library_versions':meta['library_versions']}})


if __name__=='__main__':main()
