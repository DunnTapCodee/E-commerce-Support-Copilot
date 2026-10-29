"""Build comparison figures and select a deployable configuration from measured runs."""
import json
import shutil
from pathlib import Path
import numpy as np
import pandas as pd
from services.intent_service.src.pipeline.experiments.common import json_write


def main():
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    root=Path('results/module1');report=Path('reports/module1');report.mkdir(parents=True,exist_ok=True)
    files=sorted(root.glob('*/metrics.json'))
    if not files or not (root/'latency.csv').exists():raise SystemExit('Run experiments and local latency measurement first; no synthetic results are generated')
    metrics=[json.loads(p.read_text()) for p in files]
    latency=pd.read_csv(root/'latency.csv');latency=latency[latency['mode']=='1thread'].set_index('run_id')
    rows=[];by_id={m['run_id']:m for m in metrics}
    for m in metrics:
        row={'run_id':m['run_id'],'method':m['method'],'lang':m['lang'],'ece':m['ece_after'],'size_mb':m['artifact_size_mb'],'p95_ms':float(latency.loc[m['run_id'],'p95_ms']) if m['run_id'] in latency.index else None}
        for name in ['test_clean_vi','test_noisy_vi','test_real','test_clean_en']:row[name]=m['tests'].get(name,{}).get('macro_f1')
        row['eligible']=row['p95_ms'] is not None and row['p95_ms']<10 and m.get('threshold_eligible',m.get('threshold') is not None)
        rows.append(row)
    table=pd.DataFrame(rows);table.to_csv(report/'comparison.csv',index=False)
    # A router configuration is a VI+EN pair. Require each language-specific p95<10
    # before deployment; measure the composed routing path separately after selection.
    candidates=[]
    for vi in rows:
        if vi['lang']!='vi' or not vi['eligible']:continue
        for en in rows:
            if en['lang']!='en' or not en['eligible']:continue
            score_values=[vi['test_noisy_vi'],vi['test_real'],en['test_clean_en']]
            if any(v is None for v in score_values):continue
            candidates.append({'mode':'router','vi':vi['run_id'],'en':en['run_id'],'score':float(np.mean(score_values))})
    for row in rows:
        values=[row['test_noisy_vi'],row['test_real'],row['test_clean_en']]
        if row['lang']=='multi' and row['eligible'] and all(v is not None for v in values):candidates.append({'mode':'multilingual','multi':row['run_id'],'score':float(np.mean(values))})
    selected=max(candidates,key=lambda r:r['score']) if candidates else None
    json_write(root/'selection.json',selected)
    selected_ids=[selected[k] for k in ['vi','en','multi'] if selected and k in selected]
    for run_id in selected_ids:
        curve=root/run_id/'coverage_curve.png'
        if curve.exists() and not (report/'coverage_curve.png').exists():shutil.copy2(curve,report/'coverage_curve.png')
        confusion=next(iter((root/run_id).glob('confusion_top20_*.csv')),None)
        if confusion:
            pd.read_csv(confusion).head(10).to_csv(report/f'confusion_selected_{run_id}.csv',index=False)
    noisy=table.dropna(subset=['test_noisy_vi','p95_ms'])
    fig,ax=plt.subplots()
    for row in noisy.to_dict('records'):
        ax.scatter(row['p95_ms'],row['test_noisy_vi']);ax.annotate(row['method'],(row['p95_ms'],row['test_noisy_vi']))
    ax.set(xlabel='Local CPU p95 (ms), one thread',ylabel='Macro-F1 noisy VI');ax.axvline(10,color='red',linestyle='--');fig.savefig(report/'tradeoff.png',bbox_inches='tight');plt.close(fig)
    per_intent={}
    for row in table.sort_values('test_noisy_vi',ascending=False).drop_duplicates('method').to_dict('records'):
        candidates_f1=list((root/row['run_id']).glob('per_intent_f1_test_noisy_vi.csv'))
        if candidates_f1:per_intent[row['method']]=pd.read_csv(candidates_f1[0]).set_index('intent').f1
    if per_intent:
        heat=pd.DataFrame(per_intent);fig,ax=plt.subplots(figsize=(max(7,len(heat.columns)),16));im=ax.imshow(heat.fillna(0),aspect='auto',vmin=0,vmax=1);ax.set_yticks(range(len(heat.index)),heat.index);ax.set_xticks(range(len(heat.columns)),heat.columns,rotation=45,ha='right');fig.colorbar(im,ax=ax);fig.savefig(report/'per_intent_f1.png',bbox_inches='tight');plt.close(fig)
    router=(report/'router.md').read_text() if (report/'router.md').exists() else 'Router has not been evaluated.'
    body='# Module 1 results\n\n```csv\n'+table.to_csv(index=False)+'```\n\nSelection: '+json.dumps(selected,ensure_ascii=False)+'\n\nRouter configurations require both VI and EN runs. Each language backend must meet the p95 target including routing overhead; exactly one backend runs per query. A2 is multilingual and needs no router decision for inference.\n\n'+router
    for run_id in selected_ids:
        for name in sorted(report.glob(f'confusion_selected_{run_id}.csv')):
            body+='\n\nTop confusion pairs for '+run_id+':\n```csv\n'+name.read_text()+'```\n'
    body+='\n\nTransformer configurations exceeding 10 ms remain in the table but are ineligible. No eligible configuration means deployment is blocked.\n'
    (report/'RESULTS.md').write_text(body)


if __name__=='__main__':main()
