"""k03: QC or final sentence embeddings, plus fp32/int8 MiniLM ONNX export."""
from sentence_transformers import SentenceTransformer


def run_embedding():
    if not torch.cuda.is_available():raise RuntimeError('Enable Kaggle GPU')
    model=SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',device='cuda')
    model.max_seq_length=128
    # QC is run before final datasets exist. Upload qc_pairs.parquet for this stage.
    qc=input_file('qc_pairs.parquet',required=False)
    if qc:
        pairs=pd.read_parquet(qc)
        # Chunk checkpoints allow resumption; slots are excluded from semantic content.
        import re
        clean=lambda t:preprocess(re.sub(r'\{\{[^}]+\}\}',' ',t))
        scores=[]
        for start in range(0,len(pairs),5000):
            time_budget();part=pairs.iloc[start:start+5000]
            a=model.encode([clean(t) for t in part.text_en],batch_size=256,normalize_embeddings=True,convert_to_numpy=True)
            b=model.encode([clean(t) for t in part.candidate_text],batch_size=256,normalize_embeddings=True,convert_to_numpy=True)
            score=(a*b).sum(axis=1);scores.append(score);np.save(WORK/f'qc_cos_{start:06}.npy',score)
        np.save(WORK/'qc_cos.npy',np.concatenate(scores))
    for name in ['train_multi','val_vi','val_en','test_clean_vi','test_noisy_vi','test_real','test_clean_en']:
        path=input_file(name+'.parquet',required=False)
        if path is None:continue
        frame=pd.read_parquet(path)
        output=np.lib.format.open_memmap(WORK/f'emb_{name}.npy',mode='w+',dtype='float16',shape=(len(frame),model.get_sentence_embedding_dimension()))
        for start in range(0,len(frame),5000):
            time_budget()
            output[start:start+5000]=model.encode([preprocess(t) for t in frame.text.iloc[start:start+5000]],batch_size=256,normalize_embeddings=True,convert_to_numpy=True).astype('float16');output.flush()
            save_json(WORK/f'progress_{name}.json',{'completed':min(start+5000,len(frame)),'rows':len(frame)})
        frame[['src_id','text','aug_type']].to_parquet(WORK/f'ids_{name}.parquet',index=False)
    hf=WORK/'minilm_hf';model[0].auto_model.save_pretrained(hf);model.tokenizer.save_pretrained(hf)
    export_onnx(hf,WORK/'minilm_onnx','feature-extraction')


run_embedding()
