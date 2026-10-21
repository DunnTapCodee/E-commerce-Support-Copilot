"""Generate standalone notebooks/metadata; never upload or inspect credentials."""
import argparse
import json
import re
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parent
JOBS={
    'k01-translate-en2vi':('translate.py',None),
    'k02-paraphrase-vi':('paraphrase.py',None),
    'k03-embed-minilm':('embed.py',None),
    'k04-finetune-phobert':('finetune.py', [('vinai/phobert-base-v2','vi','A1-phobert')]),
    'k05-finetune-roberta-en':('finetune.py',[('roberta-base','en','A1-roberta'),('distilroberta-base','en','A1-distilroberta')]),
}
DEPENDENCIES=['transformers==4.46.3','datasets>=3,<4','accelerate>=1,<2','sentence-transformers==3.3.1','optimum[onnxruntime]==1.23.3','onnx>=1.16,<2','onnxruntime>=1.20,<2','pyvi>=0.1.1','sentencepiece>=0.2','protobuf','pyarrow','pandas','scikit-learn','scipy']


def generate(username):
    if not re.fullmatch('[a-zA-Z0-9_-]+',username):raise ValueError('Invalid Kaggle username')
    dataset=ROOT/'datasets/ecom-intent-data';dataset.mkdir(parents=True,exist_ok=True)
    (dataset/'dataset-metadata.json').write_text(json.dumps({'title':'ecom-intent-data','id':f'{username}/ecom-intent-data','licenses':[{'name':'other'}],'isPrivate':True},indent=2))
    setup='import subprocess, sys\nsubprocess.run([sys.executable, "-m", "pip", "install", "--quiet", '+', '.join(repr(x) for x in DEPENDENCIES)+'], check=True)\n'
    for name,(job,models) in JOBS.items():
        directory=ROOT/'kernels'/name;directory.mkdir(parents=True,exist_ok=True)
        filename=name.replace('-','_')+'.ipynb'
        code=[setup,(ROOT/'jobs/common.py').read_text()]
        if models:code.append('MODEL_JOBS = '+repr(models)+'\n')
        code.append((ROOT/'jobs'/job).read_text())
        notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'name':'python3','display_name':'Python 3','language':'python'}},'cells':[
            {'cell_type':'markdown','metadata':{},'source':[f'# {name}\n','Generated from kaggle/jobs. Requires private input data; no outputs or metrics are fabricated.\n']},
            *[{'cell_type':'code','execution_count':None,'outputs':[],'metadata':{},'source':s.splitlines(keepends=True)} for s in code]]}
        (directory/filename).write_text(json.dumps(notebook,ensure_ascii=False,indent=1))
        (directory/'kernel-metadata.json').write_text(json.dumps({'id':f'{username}/{name}','title':name,'code_file':filename,'language':'python','kernel_type':'notebook','is_private':True,'enable_gpu':True,'enable_tpu':False,'enable_internet':True,'dataset_sources':[f'{username}/ecom-intent-data'],'kernel_sources':[],'competition_sources':[]},indent=2))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--username',required=True)
    parser.add_argument('--stage',nargs='*',type=Path,help='Copy specific parquet/npy checkpoint files into private dataset staging directory')
    args=parser.parse_args();generate(args.username)
    for source in args.stage or []:
        destination=ROOT/'datasets/ecom-intent-data'/source.name
        if source.is_dir():shutil.copytree(source,destination,dirs_exist_ok=True)
        elif source.is_file():shutil.copy2(source,destination)
        else:raise FileNotFoundError(source)


if __name__=='__main__':main()
