"""Stage selected artifacts and export an explicit, conservative gateway threshold."""
import argparse
import json
import shutil
import tempfile
from pathlib import Path
from services.intent_service.src.pipeline.experiments.common import json_write


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--selection',type=Path,default=Path('results/module1/selection.json'))
    parser.add_argument('--output',type=Path,default=Path('artifacts/models/intent'));args=parser.parse_args()
    choice=json.loads(args.selection.read_text())
    if not choice:raise SystemExit('No validated model meets selection criteria')
    router=args.output/'router'
    if not all((router/name).is_file() for name in ['vi_notone.txt','meta.json']):
        raise FileNotFoundError('Fit the language router before deployment')
    plans=[]
    for lang in (['multi'] if choice['mode']=='multilingual' else ['vi','en']):
        metrics=json.loads((Path('results/module1')/choice[lang]/'metrics.json').read_text())
        if not metrics.get('threshold_eligible') or metrics['threshold'] is None:raise ValueError('Validation accuracy threshold was not achieved')
        source=Path(metrics['artifact']);destination=args.output/lang
        if not (source/'meta.json').is_file():raise FileNotFoundError(source/'meta.json')
        if source.resolve()==destination.resolve():raise ValueError('Source and deployment directory must differ')
        if destination.exists():raise FileExistsError(f'{destination} exists; archive it before deployment to avoid stale files')
        plans.append((source,destination,metrics['threshold']))
    # Preflight every language before copying, and stage all copies before promotion.
    args.output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.deploy-',dir=args.output) as staging:
        for source,destination,_ in plans:shutil.copytree(source,Path(staging)/destination.name)
        for _,destination,_ in plans:shutil.move(str(Path(staging)/destination.name),str(destination))
    threshold=max(t for _,_,t in plans)
    (args.output/'deployment.env').write_text(f'INTENT_ROUTING_MODE={choice["mode"]}\nINTENT_CONFIDENCE_THRESHOLD={threshold:.2f}\n')
    json_write(args.output/'deployment.json',{'selection':choice,'gateway_threshold':threshold,'threshold_source':'validation accuracy >= 0.95; conservative maximum across routed models'})


if __name__=='__main__':main()
