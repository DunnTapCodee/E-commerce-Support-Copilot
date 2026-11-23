"""Local CPU batch-one latency, isolated worker per thread mode and artifact."""
import argparse
import importlib.metadata
import json
import os
import platform
import random
import subprocess
import sys
import time
from pathlib import Path


def worker(args):
    import numpy as np
    import pandas as pd
    from threadpoolctl import threadpool_limits
    from services.intent_service.src.predictor import BACKENDS
    from services.intent_service.src.preprocessing import preprocess
    from services.intent_service.src.router import LanguageRouter
    import importlib.util
    if args.mode=='1thread' and importlib.util.find_spec('torch') is not None:
        import torch
        torch.set_num_threads(1)
    meta=json.loads((args.artifact/'meta.json').read_text())
    router=LanguageRouter.load(args.router)
    backend=BACKENDS[meta['backend']](args.artifact,meta)
    data=pd.concat([pd.read_parquet(Path('data/processed/module1')/f'{name}.parquet') for name in ['test_clean_vi','test_noisy_vi','test_clean_en']],ignore_index=True)
    if len(data)<500:raise ValueError('Latency protocol requires 500 real held-out rows')
    texts=data.sample(n=500,random_state=42).text.tolist()
    def predict(text):
        text=preprocess(text)
        router.detect(text)
        probs=backend.predict_proba(text)
        return meta['classes'][int(np.argmax(probs))],float(np.max(probs))
    with threadpool_limits(limits=1 if args.mode=='1thread' else None):
        for i in range(50):predict(texts[i])
        durations=[]
        for text in texts:
            start=time.perf_counter();predict(text);durations.append((time.perf_counter()-start)*1000)
    row={'run_id':args.artifact.name,'mode':args.mode,'mean_ms':float(np.mean(durations)),**{f'p{q}_ms':float(np.percentile(durations,q)) for q in [50,95,99]}}
    Path(args.worker_output).write_text(json.dumps(row))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--artifacts',nargs='+',type=Path)
    parser.add_argument('--artifact',type=Path);parser.add_argument('--router',type=Path,default=Path('artifacts/models/intent/router'))
    parser.add_argument('--worker-output',type=Path);parser.add_argument('--mode',choices=['1thread','all']);args=parser.parse_args()
    if args.worker_output:worker(args);return
    import pandas as pd
    import psutil
    root=Path('results/module1');root.mkdir(parents=True,exist_ok=True)
    versions={}
    for package in ['onnxruntime','torch','scikit-learn','numpy']:
        try:versions[package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:versions[package]=None
    cpu=platform.processor()
    if sys.platform=='darwin':
        cpu=subprocess.check_output(['sysctl','-n','machdep.cpu.brand_string'],text=True).strip()
    elif Path('/proc/cpuinfo').exists():
        cpu=next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),cpu)
    (root/'latency_env.json').write_text(json.dumps({'cpu':cpu,'cores':os.cpu_count(),'ram_bytes':psutil.virtual_memory().total,'os':platform.platform(),'python':platform.python_version(),'versions':versions},indent=2))
    artifacts=args.artifacts or list(Path('artifacts/models/intent/runs').glob('*'))
    rows=[]
    for artifact in artifacts:
        for mode in ['1thread','all']:
            output=root/f'.latency_{artifact.name}_{mode}.json'
            env=os.environ.copy()
            if mode=='1thread':
                for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS','INTENT_NUM_THREADS']:env[key]='1'
            else:
                for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS','INTENT_NUM_THREADS']:env.pop(key,None)
            subprocess.run([sys.executable,'-m',__spec__.name,'--artifact',str(artifact),'--router',str(args.router),'--mode',mode,'--worker-output',str(output)],env=env,check=True)
            rows.append(json.loads(output.read_text()));output.unlink()
    csv=root/'latency.csv';old=pd.read_csv(csv) if csv.exists() else pd.DataFrame()
    pd.concat([old,pd.DataFrame(rows)],ignore_index=True).drop_duplicates(['run_id','mode'],keep='last').to_csv(csv,index=False)


if __name__=='__main__':main()
