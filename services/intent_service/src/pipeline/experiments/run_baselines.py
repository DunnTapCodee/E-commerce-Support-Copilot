"""B1/B2 local CPU experiments; calibration folds keep source groups together."""
import argparse
import copy
import time
from pathlib import Path
import joblib
import numpy as np
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.feature_selection import SelectKBest,chi2
from sklearn.decomposition import TruncatedSVD
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import FeatureUnion,Pipeline
from sklearn.svm import LinearSVC
from services.intent_service.src.preprocessing import preprocess
from services.intent_service.src.pipeline.experiments.common import load_sets,record_run,make_run_id,json_write


def features():
    return FeatureUnion([
        ('word',TfidfVectorizer(preprocessor=preprocess,ngram_range=(1,2),sublinear_tf=True,min_df=2)),
        ('char',TfidfVectorizer(preprocessor=preprocess,analyzer='char_wb',ngram_range=(2,5),sublinear_tf=True,min_df=2,max_features=200000)),
    ])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--lang',choices=['vi','en'],required=True)
    parser.add_argument('--methods',nargs='+',default=['lr','svc','rf','lightgbm','mlp'],choices=['lr','svc','rf','lightgbm','mlp'])
    parser.add_argument('--artifact-root',type=Path,default=Path('artifacts/models/intent/runs'))
    args=parser.parse_args();np.random.seed(42)
    train,val,tests=load_sets(args.lang)
    # Vectorizer is fitted solely on training text; folds group augmented siblings.
    vectorizer=features();X=vectorizer.fit_transform(train.text);V=vectorizer.transform(val.text)
    folds=list(StratifiedGroupKFold(n_splits=3,shuffle=True,random_state=42).split(X,train.intent,train.group_id))
    for method in args.methods:
        start=time.perf_counter();transform=None
        if method=='lr':
            candidates=[LogisticRegression(C=c,max_iter=2000,class_weight='balanced',random_state=42) for c in [1,5,10,20]]
        elif method=='svc':candidates=[LinearSVC(C=c,random_state=42) for c in [.1,.5,1]]
        elif method=='rf':
            transform=SelectKBest(chi2,k=min(20000,X.shape[1]));candidates=[RandomForestClassifier(n_estimators=300,n_jobs=-1,class_weight='balanced_subsample',random_state=42)]
        elif method=='lightgbm':
            from lightgbm import LGBMClassifier
            transform=SelectKBest(chi2,k=min(20000,X.shape[1]));candidates=[LGBMClassifier(objective='multiclass',n_estimators=500,learning_rate=.1,num_leaves=63,random_state=42,verbosity=-1)]
        else:
            transform=TruncatedSVD(n_components=min(300,X.shape[1]-1,X.shape[0]-1),random_state=42)
            candidates=[MLPClassifier(hidden_layer_sizes=(256,),early_stopping=True,random_state=42,max_iter=300)]
        Xfit=transform.fit_transform(X,train.intent) if transform is not None else X
        Vfit=transform.transform(V) if transform is not None else V
        best,score=None,-1.
        for estimator in candidates:
            if method=='lightgbm':
                from lightgbm import early_stopping
                estimator.fit(Xfit,train.intent,eval_set=[(Vfit,val.intent)],callbacks=[early_stopping(30,verbose=False)])
            else:estimator.fit(Xfit,train.intent)
            value=f1_score(val.intent,estimator.predict(Vfit),average='macro',zero_division=0)
            if value>score:best,score=estimator,value
        if hasattr(best,'predict_proba'):
            before=best.predict_proba(Vfit)
        else:
            from scipy.special import softmax
            before=softmax(best.decision_function(Vfit),axis=1)
        if method!='lr':
            selected=clone(best)
            if method=='lightgbm' and getattr(best,'best_iteration_',0):selected.set_params(n_estimators=best.best_iteration_)
            calibrated=CalibratedClassifierCV(selected,method='sigmoid',cv=folds,n_jobs=1)
            calibrated.fit(Xfit,train.intent);best=calibrated
        steps=[('features',copy.deepcopy(vectorizer))]
        if transform is not None:steps.append(('reduce',transform))
        steps.append(('classifier',best));model=Pipeline(steps)
        name=f'B1-{method}' if method in ['lr','svc'] else f'B2-{method}'
        artifact=args.artifact_root/make_run_id(name,args.lang);artifact.mkdir(parents=True)
        joblib.dump(model,artifact/'model.joblib')
        record_run(model,artifact,name,args.lang,len(train),time.perf_counter()-start,val,tests,raw_validation_probs=before)
        json_write(artifact/'training_config.json',{'best_val_macro_f1':score,'seed':42,'group_calibration':True})


if __name__=='__main__':main()
