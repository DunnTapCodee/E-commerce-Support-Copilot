"""k04/k05: GPU transformer training, held-out logits, temperature and ONNX."""
from datasets import Dataset
from sklearn.metrics import classification_report,f1_score,accuracy_score
from scipy.optimize import minimize_scalar
from scipy.special import softmax
from transformers import AutoTokenizer,AutoModelForSequenceClassification,DataCollatorWithPadding,Trainer,TrainingArguments,TrainerCallback


class BudgetCallback(TrainerCallback):
    def on_step_end(self,args,state,control,**kwargs):
        if time.monotonic()-START>5.25*3600:
            control.should_save=True;control.should_training_stop=True
        return control


def finetune_one(name,lang,tag):
    from importlib.metadata import version
    if not torch.cuda.is_available():raise RuntimeError('Enable Kaggle GPU')
    root=WORK/tag;root.mkdir(exist_ok=True)
    # Previous checkpoints may be attached as a private dataset directory.
    if not (root/'checkpoints').exists():
        import shutil
        prior=[p for p in Path('/kaggle/input').rglob('checkpoints') if p.parent.name==tag]
        if len(prior)>1:raise ValueError('Multiple checkpoint sources for '+tag)
        if prior:shutil.copytree(prior[0],root/'checkpoints')
    train=pd.read_parquet(input_file(f'train_{lang}.parquet'));val=pd.read_parquet(input_file(f'val_{lang}.parquet'))
    labels=sorted(train.intent.unique());label2id={s:i for i,s in enumerate(labels)}
    tokenizer=AutoTokenizer.from_pretrained(name)
    prepare=segment_vi if lang=='vi' else preprocess
    def dataset(frame):
        ds=Dataset.from_dict({'text':[prepare(t) for t in frame.text],'labels':[label2id[i] for i in frame.intent]})
        return ds.map(lambda row:tokenizer(row['text'],truncation=True,max_length=64),batched=True,remove_columns=['text'])
    model=AutoModelForSequenceClassification.from_pretrained(name,num_labels=len(labels),id2label=dict(enumerate(labels)),label2id=label2id)
    args=TrainingArguments(output_dir=str(root/'checkpoints'),learning_rate=2e-5,per_device_train_batch_size=32,per_device_eval_batch_size=64,num_train_epochs=4,warmup_ratio=.1,weight_decay=.01,fp16=True,eval_strategy='epoch',save_strategy='epoch',load_best_model_at_end=True,metric_for_best_model='macro_f1',greater_is_better=True,seed=42,data_seed=42,save_total_limit=2,report_to='none')
    trainer=Trainer(model=model,args=args,train_dataset=dataset(train),eval_dataset=dataset(val),data_collator=DataCollatorWithPadding(tokenizer),compute_metrics=lambda r:{'macro_f1':f1_score(r.label_ids,np.argmax(r.predictions,axis=1),average='macro')},callbacks=[BudgetCallback()])
    checkpoints=sorted((root/'checkpoints').glob('checkpoint-*'),key=lambda p:int(p.name.split('-')[-1]))
    train_start=time.monotonic()
    trainer.train(resume_from_checkpoint=str(checkpoints[-1]) if checkpoints else None)
    train_time=time.monotonic()-train_start
    if trainer.state.epoch is None or trainer.state.epoch<3.99:
        raise RuntimeError('Training stopped at time budget; attach checkpoints and resume before exporting a final model')
    trainer.save_model(root/'model');tokenizer.save_pretrained(root/'model')
    vp=trainer.predict(dataset(val));logits=vp.predictions
    def nll(temp):
        p=softmax(logits/temp,axis=1)
        return -np.log(np.clip(p[np.arange(len(val)),vp.label_ids],1e-12,1)).mean()
    temperature=float(minimize_scalar(nll,bounds=(.05,10),method='bounded').x)
    np.save(root/'logits_val.npy',logits);val[['src_id','text','intent','aug_type']].to_parquet(root/'ids_val.parquet',index=False)
    calibrated=softmax(logits/temperature,axis=1);confidence=calibrated.max(axis=1);pred=calibrated.argmax(axis=1)
    threshold=None
    for t in np.round(np.arange(.3,.951,.01),2):
        kept=confidence>=t
        if kept.any() and np.mean(pred[kept]==vp.label_ids[kept])>=.95:threshold=float(t);break
    def ece(y,p):
        conf=p.max(axis=1);correct=p.argmax(axis=1)==y;total=0.
        for i in range(15):
            mask=(conf>=i/15)&((conf<(i+1)/15) if i<14 else conf<=1)
            if mask.any():total+=mask.mean()*abs(correct[mask].mean()-conf[mask].mean())
        return float(total)
    metrics={'method':tag,'train_time_s':train_time,'lang':lang,'threshold':threshold,'threshold_eligible':threshold is not None,'temperature':temperature,'train_size':len(train),'ece_before':ece(vp.label_ids,softmax(logits,axis=1)),'ece_after':ece(vp.label_ids,calibrated),'tests':{}}
    tests=['test_clean_vi','test_noisy_vi','test_real'] if lang=='vi' else ['test_clean_en']
    for test in tests:
        frame=pd.read_parquet(input_file(test+'.parquet'));prediction=trainer.predict(dataset(frame));scores=prediction.predictions;probs=softmax(scores/temperature,axis=1);yhat=np.asarray(labels)[probs.argmax(axis=1)]
        np.save(root/f'logits_{test}.npy',scores);frame[['src_id','text','intent','aug_type']].to_parquet(root/f'ids_{test}.parquet',index=False)
        metrics['tests'][test]={'macro_f1':float(f1_score(frame.intent,yhat,average='macro')),'accuracy':float(accuracy_score(frame.intent,yhat)),'ece':ece(prediction.label_ids,probs)}
        report=classification_report(frame.intent,yhat,labels=labels,output_dict=True,zero_division=0)
        pd.DataFrame([{'intent':s,'precision':report[s]['precision'],'recall':report[s]['recall'],'f1':report[s]['f1-score'],'support':report[s]['support']} for s in labels]).to_csv(root/f'per_intent_f1_{test}.csv',index=False)
    meta={'backend':'onnx_transformer','method':tag,'lang':lang,'classes':labels,'max_length':64,'temperature':temperature,'threshold':threshold,'needs_word_segmentation':lang=='vi','library_versions':{'transformers':version('transformers'),'torch':version('torch')},'metrics':metrics['tests']}
    export_onnx(root/'model',root/'onnx','text-classification')
    save_json(root/'meta.json',meta);save_json(root/'metrics_kaggle.json',metrics)


# MODEL_JOBS is assigned by the generated notebook's configuration cell.
for model_name,language,tag in MODEL_JOBS:
    time_budget();finetune_one(model_name,language,tag)
