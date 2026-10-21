"""Optional measurement of the explicitly archived model; never used by serving."""
import argparse
from pathlib import Path
import joblib
import numpy as np


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model-dir',type=Path,default=Path('artifacts/models/legacy_linearsvc_en'));args=parser.parse_args()
    model=joblib.load(args.model_dir/'model_intent_full.pkl')
    vectorizer=joblib.load(args.model_dir/'tfidf_vectorizer_full.pkl')
    encoder=joblib.load(args.model_dir/'label_encoder_full.pkl')
    rows=[]
    for text in ['Tôi muốn hủy đơn hàng vừa đặt','toi muon huy don hang','phí ship bao nhiêu','I want to cancel my order','where is my order']:
        features=vectorizer.transform([text]);scores=model.decision_function(features)[0];index=int(np.argmax(scores))
        confidence=.10 if features.nnz==0 else float(1/(1+np.exp(-scores[index])))
        rows.append(f'| {text} | {encoder.classes_[index]} | {confidence:.4f} |')
    output=Path('reports/module1/legacy_baseline.md');output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text('# Legacy baseline\n\nExplicit archived artifact; historical sigmoid-margin confidence, not calibrated probability.\n\n| Query | Intent | Confidence |\n|---|---|---|\n'+'\n'.join(rows)+'\n')


if __name__=='__main__':main()
