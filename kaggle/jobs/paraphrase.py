"""k02: two sampled VI translations per training instruction, checkpointed."""
from transformers import AutoTokenizer,AutoModelForSeq2SeqLM


def run_paraphrases():
    if not torch.cuda.is_available():raise RuntimeError('Enable Kaggle GPU')
    inputs=pd.read_parquet(input_file('translation_input.parquet'))
    translated=pd.read_parquet(input_file('bitext_vi_translated.parquet'))
    train=inputs[inputs.split=='train'].sort_values('text_en',key=lambda s:s.str.len())
    checkpoint=WORK/'paraphrase_partial.parquet';prior=input_file('paraphrase_partial.parquet',required=False)
    rows=pd.read_parquet(checkpoint if checkpoint.exists() else prior).to_dict('records') if checkpoint.exists() or prior else []
    train=train[~train.src_id.isin({r['src_id'] for r in rows})]
    name='vinai/vinai-translate-en2vi-v2';tok=AutoTokenizer.from_pretrained(name,src_lang='en_XX');model=AutoModelForSeq2SeqLM.from_pretrained(name).half().cuda().eval()
    target=tok.lang_code_to_id['vi_VN'] if hasattr(tok,'lang_code_to_id') else tok.convert_tokens_to_ids('vi_VN')
    try:
        for offset in range(0,len(train),64):
            time_budget();batch=train.iloc[offset:offset+64]
            encoded=tok(batch.text_en.tolist(),return_tensors='pt',padding=True,truncation=True,max_length=128).to('cuda')
            with torch.inference_mode():out=model.generate(**encoded,decoder_start_token_id=target,do_sample=True,top_p=.9,temperature=.8,num_return_sequences=2,max_new_tokens=128)
            texts=tok.batch_decode(out,skip_special_tokens=True)
            rows.extend({'src_id':sid,'vi_para_1':texts[2*i],'vi_para_2':texts[2*i+1]} for i,sid in enumerate(batch.src_id))
            if offset%4992==0:pd.DataFrame(rows).to_parquet(checkpoint,index=False)
    finally:
        if rows:pd.DataFrame(rows).to_parquet(checkpoint,index=False)
    update=pd.DataFrame(rows).set_index('src_id');translated=translated.set_index('src_id');translated.update(update)
    translated.reset_index().to_parquet(WORK/'bitext_vi_translated.parquet',index=False)


run_paraphrases()
