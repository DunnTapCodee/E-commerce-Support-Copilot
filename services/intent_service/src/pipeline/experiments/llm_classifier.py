"""Zero/few-shot intent assignment through an OpenAI-compatible chat API (labels only, no calibration)."""
import hashlib
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx

DEFAULT_BASE = 'https://api.xah.io/v1'
INVALID = 'invalid_llm_output'


class LLMIntentClassifier:
    def __init__(self, labels, model=None, api_base=None, api_key=None, workers=8, cache=Path('results/intent_eval_en/llm_cache.jsonl'), timeout=60., retries=3, examples=None):
        self.labels = list(labels)
        self.model = model or os.getenv('LLM_MODEL', 'gpt-4o-mini')
        self.api_base = (api_base or os.getenv('LLM_API_BASE', DEFAULT_BASE)).rstrip('/')
        self.api_key = api_key or os.getenv('LLM_API_KEY', '')
        if not self.api_key:
            raise ValueError('Set LLM_API_KEY (or pass api_key)')
        self.workers, self.retries, self.timeout = workers, retries, timeout
        self.cache_path, self._lock = Path(cache), threading.Lock()
        self.cache = {}
        if self.cache_path.exists():
            for line in self.cache_path.read_text().splitlines():
                row = json.loads(line);self.cache[row['key']] = row['label']
        self.system = self._system_prompt(examples or {})

    def _system_prompt(self, examples):
        lines = ['You are an intent classifier for an e-commerce customer-support assistant.',
                 'Classify the customer message into exactly ONE of these intents:', ', '.join(self.labels), '']
        for label, texts in examples.items():
            lines += [f'Examples of {label}:'] + [f'- {t}' for t in texts]
        lines += ['', 'Reply with JSON only, in the form {"intent": "<one intent from the list>"}.']
        return '\n'.join(lines)

    def _key(self, text):
        return hashlib.sha256(f'{self.model}\n{self.system}\n{text}'.encode()).hexdigest()

    def _parse(self, content):
        match = re.search(r'\{.*?\}', content or '', re.S)
        value = None
        if match:
            try:value = str(json.loads(match.group(0)).get('intent', '')).strip()
            except ValueError:pass
        if value is None:value = (content or '').strip().strip('"\'`')
        value = value.lower().replace(' ', '_').replace('-', '_')
        return value if value in self.labels else INVALID

    def _call(self, client, text):
        body = {'model': self.model, 'temperature': 0, 'max_tokens': 40,
                'messages': [{'role': 'system', 'content': self.system}, {'role': 'user', 'content': text}]}
        error = None
        for attempt in range(self.retries):
            try:
                r = client.post(f'{self.api_base}/chat/completions', json=body, headers={'Authorization': f'Bearer {self.api_key}'})
                r.raise_for_status()
                return self._parse(r.json()['choices'][0]['message']['content'])
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                error = exc
                import time;time.sleep(2 ** attempt)
        raise RuntimeError(f'LLM request failed after {self.retries} attempts: {error}')

    def predict(self, texts):
        texts = list(texts)
        todo = sorted({t for t in texts if self._key(t) not in self.cache})
        if todo:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with httpx.Client(timeout=self.timeout) as client, self.cache_path.open('a') as out, ThreadPoolExecutor(self.workers) as pool:
                for text, label in zip(todo, pool.map(lambda t: self._call(client, t), todo)):
                    key = self._key(text);self.cache[key] = label
                    with self._lock:out.write(json.dumps({'key': key, 'label': label}) + '\n');out.flush()
        return [self.cache[self._key(t)] for t in texts]
