"""Optional explicit paid-API translation with cache and three attempts per batch."""
import argparse
import json
import os
import time
from pathlib import Path
import httpx
import pandas as pd
from services.intent_service.src.pipeline.data.placeholders import TOKEN


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,default=Path('data/interim/translation_input.parquet'))
    parser.add_argument('--output',type=Path,default=Path('data/interim/llm_translated.parquet'))
    parser.add_argument('--allow-paid-api',action='store_true',required=True)
    args=parser.parse_args()
    key=os.getenv('LLM_API_KEY');provider=os.getenv('LLM_PROVIDER')
    if not key or provider!='openai-compatible':
        raise SystemExit('Explicit LLM_API_KEY and LLM_PROVIDER=openai-compatible required; no credential discovery')
    url=os.environ['LLM_API_URL'];model=os.environ['LLM_MODEL']
    source=pd.read_parquet(args.input)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    done=pd.read_parquet(args.output).to_dict('records') if args.output.exists() else []
    pending=source[~source.src_id.isin({r['src_id'] for r in done})]
    rejected=args.output.with_suffix('.rejected.jsonl')
    with httpx.Client(timeout=120) as client:
        for offset in range(0,len(pending),50):
            batch=pending.iloc[offset:offset+50];items=[{'id':r.src_id,'en':r.text_en} for r in batch.itertuples()]
            prompt='Translate instructions to Vietnamese, preserving slang, profanity, abbreviations and typos. Preserve every [[SLOTn]] exactly. Do not translate answers. Return ONLY a JSON array [{"id":...,"vi":...,"para":[..., ...]}].\n'+json.dumps(items,ensure_ascii=False)
            error=None
            for attempt in range(3):
                try:
                    response=client.post(url,headers={'Authorization':f'Bearer {key}'},json={'model':model,'messages':[{'role':'user','content':prompt}],'temperature':.3})
                    response.raise_for_status();payload=json.loads(response.json()['choices'][0]['message']['content'])
                    by_id={r['id']:r for r in payload}
                    if set(by_id)!={r['id'] for r in items}:raise ValueError('Missing, duplicate, or unexpected source IDs')
                    accepted=[]
                    for item in items:
                        row=by_id[item['id']]
                        if not isinstance(row.get('vi'),str) or not row['vi'].strip():raise ValueError('Refused or empty translation')
                        if sorted(TOKEN.findall(row['vi']))!=sorted(TOKEN.findall(item['en'])):raise ValueError('Lost translation slots')
                        paras=row.get('para',[])
                        accepted.append({'src_id':item['id'],'text_en':item['en'],'text_vi':row['vi'],'vi_para_1':paras[0] if len(paras)>0 else '', 'vi_para_2':paras[1] if len(paras)>1 else '', 'translator':f'llm:{model}'})
                    done.extend(accepted);pd.DataFrame(done).to_parquet(args.output,index=False);error=None;break
                except (httpx.HTTPError,ValueError,KeyError,TypeError,IndexError) as exc:
                    error=str(exc)
                    if attempt<2:time.sleep(2**attempt)
            if error:
                with rejected.open('a') as handle:handle.write(json.dumps({'ids':[x['id'] for x in items],'error':error})+'\n')
                raise SystemExit('Translation failed after three attempts; review rejection log before resuming')


if __name__=='__main__':main()
