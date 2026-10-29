"""Shared metrics, validation-only threshold selection and artifact metadata."""
import importlib.metadata
import json
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

DATA = Path('data/processed/module1')
RESULTS = Path('results/module1')


def json_write(path, payload):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False))


def ece(y, probs, classes, bins=15):
    labels=np.asarray(classes);pred=labels[probs.argmax(axis=1)];conf=probs.max(axis=1)
    total=0.
    for i in range(bins):
        mask=(conf>=i/bins)&((conf<(i+1)/bins) if i<bins-1 else (conf<=1))
        if mask.any():total+=mask.mean()*abs(np.mean(pred[mask]==np.asarray(y)[mask])-conf[mask].mean())
    return float(total)


def select_threshold(y,probs,classes):
    pred=np.asarray(classes)[probs.argmax(axis=1)];conf=probs.max(axis=1)
    curve=[]
    for t in np.round(np.arange(.30,.951,.01),2):
        keep=conf>=t
        curve.append({'threshold':float(t),'coverage':float(keep.mean()),'accuracy':float(np.mean(pred[keep]==np.asarray(y)[keep])) if keep.any() else None})
    eligible=[r for r in curve if r['accuracy'] is not None and r['accuracy']>=.95]
    return (eligible[0] if eligible else None),curve


def make_run_id(method,lang):
    # Seconds avoid silently overwriting same-minute hyperparameter runs.
    return f'{method}_{lang}_{datetime.now().strftime("%Y%m%d-%H%M%S")}'


def write_meta(path,method,lang,classes,threshold,backend='sklearn',**extra):
    json_write(Path(path)/'meta.json',{'backend':backend,'method':method,'lang':lang,'classes':list(map(str,classes)),
        'threshold':threshold,'temperature':1.,'max_length':64,'needs_word_segmentation':False,
        'created_at':datetime.now().astimezone().isoformat(),
        'library_versions':{'scikit-learn':importlib.metadata.version('scikit-learn')},**extra})


def evaluate_predictions(run_dir,name,y,probs,classes):
    predictions=np.asarray(classes)[probs.argmax(axis=1)]
    report=classification_report(y,predictions,labels=list(classes),output_dict=True,zero_division=0)
    pd.DataFrame([{'intent':label,**{'precision':report[label]['precision'],'recall':report[label]['recall'],'f1':report[label]['f1-score'],'support':report[label]['support']}} for label in classes]).to_csv(run_dir/f'per_intent_f1_{name}.csv',index=False)
    matrix=confusion_matrix(y,predictions,labels=list(classes))
    pairs=sorted([{'true':a,'pred':b,'count':int(matrix[i,j])} for i,a in enumerate(classes) for j,b in enumerate(classes) if i!=j and matrix[i,j]],key=lambda r:r['count'],reverse=True)[:20]
    pd.DataFrame(pairs,columns=['true','pred','count']).to_csv(run_dir/f'confusion_top20_{name}.csv',index=False)
    return {'macro_f1':float(f1_score(y,predictions,average='macro',zero_division=0)),'accuracy':float(accuracy_score(y,predictions)),'ece':ece(y,probs,classes)}


def record_run(model,artifact,method,lang,train_size,train_time,validation,testsets,raw_validation_probs=None,extra=None):
    run_id=Path(artifact).name;run_dir=RESULTS/run_id;run_dir.mkdir(parents=True,exist_ok=True)
    classes=list(map(str,model.classes_));vp=model.predict_proba(validation.text)
    selected,curve=select_threshold(validation.intent,vp,classes)
    # None means the desired accuracy could not be established; deployment refuses it.
    threshold=selected['threshold'] if selected else None
    metrics={'run_id':run_id,'method':method,'lang':lang,'train_size':train_size,'train_time_s':train_time,
             'threshold':threshold,'threshold_eligible':selected is not None,'coverage_at_threshold':selected['coverage'] if selected else 0.,
             'ece_before':ece(validation.intent,raw_validation_probs,classes) if raw_validation_probs is not None else None,
             'ece_after':ece(validation.intent,vp,classes),'sklearn_version':importlib.metadata.version('scikit-learn'),
             'artifact':str(Path(artifact).resolve()),'artifact_size_mb':sum(p.stat().st_size for p in Path(artifact).rglob('*') if p.is_file())/1024**2,
             'tests':{},**(extra or {})}
    for name,test in testsets.items():
        if test.empty:continue
        metrics['tests'][name]=evaluate_predictions(run_dir,name,test.intent,model.predict_proba(test.text),classes)
    json_write(run_dir/'coverage_curve.json',curve)
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots();ax.plot([r['coverage'] for r in curve],[r['accuracy'] if r['accuracy'] is not None else np.nan for r in curve]);ax.set(xlabel='Coverage',ylabel='Accuracy');fig.savefig(run_dir/'coverage_curve.png',bbox_inches='tight');plt.close(fig)
    json_write(run_dir/'metrics.json',metrics)
    meta_extra=(extra or {}).get('meta',{})
    write_meta(artifact,method,lang,classes,threshold,metrics=metrics['tests'],**meta_extra)
    row={k:v for k,v in metrics.items() if not isinstance(v,(list,dict))}
    for name,result in metrics['tests'].items():row.update({f'{name}_{k}':v for k,v in result.items()})
    csv=RESULTS/'metrics.csv'
    existing=pd.read_csv(csv) if csv.exists() else pd.DataFrame()
    pd.concat([existing,pd.DataFrame([row])],ignore_index=True).drop_duplicates('run_id',keep='last').to_csv(csv,index=False)
    return metrics


def load_sets(lang):
    names=['test_clean_vi','test_noisy_vi','test_real'] if lang=='vi' else ['test_clean_en']
    if lang=='multi':names=['test_clean_vi','test_noisy_vi','test_real','test_clean_en']
    train=pd.read_parquet(DATA/f'train_{lang}.parquet')
    val=pd.concat([pd.read_parquet(DATA/'val_vi.parquet'),pd.read_parquet(DATA/'val_en.parquet')],ignore_index=True) if lang=='multi' else pd.read_parquet(DATA/f'val_{lang}.parquet')
    return train,val,{n:pd.read_parquet(DATA/f'{n}.parquet') for n in names}
