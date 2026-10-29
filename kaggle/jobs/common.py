"""Shared source embedded into each generated standalone Kaggle notebook."""
import os
os.environ['TOKENIZERS_PARALLELISM']='false'
import json
import random
import subprocess
import time
from pathlib import Path
import numpy as np
import pandas as pd
import torch
import transformers

SEED=42
random.seed(SEED);np.random.seed(SEED);torch.manual_seed(SEED)
if torch.cuda.is_available():torch.cuda.manual_seed_all(SEED)
print(subprocess.run(['nvidia-smi'],capture_output=True,text=True).stdout)
print({'torch':torch.__version__,'transformers':transformers.__version__,'seed':SEED})
WORK=Path('/kaggle/working');WORK.mkdir(exist_ok=True)
INPUT=Path('/kaggle/input/ecom-intent-data')
START=time.monotonic()


def input_file(name,required=True):
    candidates=sorted(Path('/kaggle/input').rglob(name))
    if not candidates:
        if required:raise FileNotFoundError(f'Upload {name} to the private ecom-intent-data dataset')
        return None
    if len(candidates)>1:
        raise ValueError(f'Ambiguous input {name}: {candidates}. Attach only one data version.')
    return candidates[0]


def save_json(path,data):
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False))


def time_budget():
    if time.monotonic()-START>5.5*3600:
        raise RuntimeError('5.5 hour budget reached. Download checkpoint, attach it to the dataset, then resume.')


def normalize_text(text):
    import re,unicodedata
    return re.sub(r'\s+',' ',unicodedata.normalize('NFC',text)).strip()


def preprocess(text):return normalize_text(text).lower()


def segment_vi(text):
    from pyvi import ViTokenizer
    return ViTokenizer.tokenize(preprocess(text))


def export_onnx(source,destination,task):
    """GPU export in Kaggle; local work only consumes the exported ONNX."""
    from optimum.onnxruntime import ORTModelForFeatureExtraction,ORTModelForSequenceClassification,ORTQuantizer
    from optimum.onnxruntime.configuration import AutoQuantizationConfig
    cls=ORTModelForFeatureExtraction if task=='feature-extraction' else ORTModelForSequenceClassification
    exported=cls.from_pretrained(str(source),export=True)
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    exported.save_pretrained(destination)
    quantizer=ORTQuantizer.from_pretrained(exported)
    quantizer.quantize(save_dir=destination,quantization_config=AutoQuantizationConfig.avx2(is_static=False,per_channel=False),file_suffix='int8')
    from transformers import AutoTokenizer
    AutoTokenizer.from_pretrained(str(source)).save_pretrained(destination)
