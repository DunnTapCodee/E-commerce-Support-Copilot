"""k01: translate unique protected instructions; paraphrases are delegated to k02."""
from transformers import AutoTokenizer,AutoModelForSeq2SeqLM


def run_translation():
    if not torch.cuda.is_available():raise RuntimeError('Enable GPU and Internet on the verified Kaggle account')
    frame=pd.read_parquet(input_file('translation_input.parquet')).sort_values('text_en',key=lambda s:s.str.len())
    output=WORK/'translated_partial.parquet'
    checkpoint=input_file('translated_partial.parquet',required=False)
    done=pd.read_parquet(output if output.exists() else checkpoint).to_dict('records') if output.exists() or checkpoint else []
    frame=frame[~frame.src_id.isin({r['src_id'] for r in done})]
    name='vinai/vinai-translate-en2vi-v2';nllb=False
    try:
        tok=AutoTokenizer.from_pretrained(name,src_lang='en_XX')
        model=AutoModelForSeq2SeqLM.from_pretrained(name).half().cuda().eval()
    except (OSError,ValueError,RuntimeError) as exc:
        print('Default translator unavailable:',str(exc));name='facebook/nllb-200-distilled-600M';nllb=True
        tok=AutoTokenizer.from_pretrained(name,src_lang='eng_Latn')
        model=AutoModelForSeq2SeqLM.from_pretrained(name).half().cuda().eval()
    target='vie_Latn' if nllb else 'vi_VN'
    target_id=tok.lang_code_to_id[target] if hasattr(tok,'lang_code_to_id') else tok.convert_tokens_to_ids(target)
    if target_id is None or target_id==tok.unk_token_id:raise ValueError('Tokenizer does not recognize target language token')
    since_save=0
    try:
        for offset in range(0,len(frame),64):
            time_budget();batch=frame.iloc[offset:offset+64]
            encoded=tok(batch.text_en.tolist(),return_tensors='pt',padding=True,truncation=True,max_length=128).to('cuda')
            kwargs={'forced_bos_token_id':target_id} if nllb else {'decoder_start_token_id':target_id}
            with torch.inference_mode():out=model.generate(**encoded,**kwargs,num_beams=5,early_stopping=True,max_new_tokens=128)
            translations=tok.batch_decode(out,skip_special_tokens=True)
            for row,vi in zip(batch.to_dict('records'),translations):
                done.append({'src_id':row['src_id'],'text_en':row['text_en'],'text_vi':vi,'vi_para_1':'','vi_para_2':'','translator':name})
            since_save+=len(batch)
            if since_save>=5000:pd.DataFrame(done).to_parquet(output,index=False);since_save=0
    finally:
        if done:pd.DataFrame(done).to_parquet(output,index=False)
    pd.DataFrame(done).sort_values('src_id').to_parquet(WORK/'bitext_vi_translated.parquet',index=False)
    save_json(WORK/'translation_status.json',{'complete':True,'rows':len(done),'paraphrases':'Run k02 for train only to keep each kernel below six hours'})


run_translation()
