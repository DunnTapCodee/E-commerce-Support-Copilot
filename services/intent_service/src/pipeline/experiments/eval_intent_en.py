"""English intent-assignment comparison: TF-IDF + {LinearSVC, LR, XGBoost, LightGBM, RF} vs. an LLM.

Everything is reported per model, per intent and per data slice (clean/noisy, length, Bitext style tags)."""
import hashlib
import random
import re
import unicodedata
import time
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.feature_selection import SelectKBest, chi2
from sklearn.metrics import accuracy_score, f1_score, precision_recall_fscore_support
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import LabelEncoder

# Self-contained on purpose: this file + llm_classifier.py must run alone (e.g. on Kaggle without the repo).
def preprocess(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', text)).strip().lower()


def typo(text, rng):
    """English typo noise: delete/repeat/swap a character in 1-2 words."""
    words = text.split()
    if len(words) < 3:
        return text
    candidates = [i for i, w in enumerate(words) if w.isalpha() and len(w) >= 3]
    for i in rng.sample(candidates, min(len(candidates), rng.randint(1, 2))):
        w = words[i];j = rng.randrange(len(w) - 1);op = rng.choice(['delete', 'repeat', 'swap'])
        words[i] = w[:j] + w[j + 1:] if op == 'delete' else w[:j] + w[j] + w[j:] if op == 'repeat' else w[:j] + w[j + 1] + w[j] + w[j + 2:]
    return ' '.join(words)


def group_id(text):
    key = re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', re.sub(r'\{\{.*?\}\}', ' slot ', preprocess(text)))).strip()
    return hashlib.sha256(key.encode()).hexdigest()[:20]

PROCESSED = Path('data/processed/module1')
OUT = Path('results/intent_eval_en')
# Bitext linguistic-variation tags; documented in the dataset card.
STYLE = {'B': 'basic', 'I': 'interrogative', 'C': 'coordinated', 'N': 'negation', 'M': 'morphological', 'L': 'lexical',
         'E': 'abbreviation', 'P': 'politeness', 'Q': 'colloquial', 'W': 'offensive', 'K': 'keyword', 'Z': 'noisy'}


def length_bucket(text):
    n = len(str(text).split())
    return '1-4 words' if n <= 4 else '5-8 words' if n <= 8 else '9-14 words' if n <= 14 else '15+ words'


def add_noise(frame, seed=1234):
    rng = random.Random(seed);noisy = frame.copy()
    noisy['text'] = [typo(t, rng) for t in noisy.text];noisy['dtype'] = 'noisy_typo'
    return noisy


def load_en_data(seed=42):
    """Use the Module 1 parquet splits when built; otherwise split raw Bitext by normalized-text group."""
    if (PROCESSED / 'train_en.parquet').exists():
        train, val, test = (pd.read_parquet(PROCESSED / f'{n}_en.parquet') for n in ['train', 'val', 'test_clean'])
        test = test.assign(dtype='clean')
    else:
        from datasets import load_dataset
        from sklearn.model_selection import GroupShuffleSplit
        raw = load_dataset('bitext/Bitext-retail-ecommerce-llm-chatbot-training-dataset', split='train').to_pandas()
        raw = raw.rename(columns={'instruction': 'text'})[['text', 'intent', 'tags']]
        raw['group_id'] = raw.text.map(group_id)
        outer = GroupShuffleSplit(1, test_size=.2, random_state=seed)
        rest, te = next(outer.split(raw, groups=raw.group_id))
        inner = GroupShuffleSplit(1, test_size=.125, random_state=seed)
        tr, va = next(inner.split(raw.iloc[rest], groups=raw.iloc[rest].group_id))
        train, val, test = raw.iloc[rest].iloc[tr], raw.iloc[rest].iloc[va], raw.iloc[te]
        test = test.assign(dtype='clean')
    if 'tags' in test:  # first matching style letter that Bitext marks for the utterance
        test['style'] = test.tags.map(lambda t: next((STYLE[c] for c in str(t) if c in STYLE and c.isupper()), 'basic'))
    tests = pd.concat([test, add_noise(test)], ignore_index=True)
    tests['length'] = tests.text.map(length_bucket)
    return train.reset_index(drop=True), val.reset_index(drop=True), tests


class SklearnIntentModel:
    """TF-IDF (word + char) -> chi2 selection -> classifier; labels are encoded for XGBoost/LightGBM."""

    def __init__(self, name, make_clf, select_k=20000, early_stopping=False):
        self.name, self.make_clf, self.select_k, self.early_stopping = name, make_clf, select_k, early_stopping

    def fit(self, train, val):
        self.enc = LabelEncoder().fit(train.intent)
        y, yv = self.enc.transform(train.intent), self.enc.transform(val.intent)
        feats = FeatureUnion([
            ('word', TfidfVectorizer(preprocessor=preprocess, ngram_range=(1, 2), sublinear_tf=True, min_df=2)),
            ('char', TfidfVectorizer(preprocessor=preprocess, analyzer='char_wb', ngram_range=(2, 5), sublinear_tf=True, min_df=2, max_features=200000))])
        X = feats.fit_transform(train.text)
        self.select = SelectKBest(chi2, k=min(self.select_k, X.shape[1])) if self.select_k else None
        if self.select is not None:
            X = self.select.fit_transform(X, y)
        self.feats = feats
        self.clf = self.make_clf(len(self.enc.classes_))
        start = time.perf_counter()
        if self.early_stopping:
            self.clf.fit(X, y, eval_set=[(self._x(val.text), yv)], **self.early_stopping_kwargs())
        else:
            self.clf.fit(X, y)
        self.train_time_s = time.perf_counter() - start
        return self

    def early_stopping_kwargs(self):
        if self.name == 'tfidf_lightgbm':
            from lightgbm import early_stopping
            return {'callbacks': [early_stopping(30, verbose=False)]}
        return {'verbose': False}  # xgboost: early_stopping_rounds is set on the estimator

    def _x(self, texts):
        X = self.feats.transform(texts)
        return self.select.transform(X) if self.select is not None else X

    def predict(self, texts):
        return self.enc.inverse_transform(np.asarray(self.clf.predict(self._x(texts))).astype(int).ravel())


ALL_MODELS = ('linearsvc', 'lr', 'sgd', 'ridge', 'pa', 'cnb', 'knn', 'rf', 'extratrees', 'mlp', 'xgboost', 'lightgbm')


def build_models(names=ALL_MODELS):
    from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression, PassiveAggressiveClassifier, RidgeClassifier, SGDClassifier
    from sklearn.naive_bayes import ComplementNB
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.neural_network import MLPClassifier
    from sklearn.svm import LinearSVC
    registry = {
        'linearsvc': lambda: SklearnIntentModel('tfidf_linearsvc', lambda k: LinearSVC(C=.5, random_state=42), select_k=None),
        'lr': lambda: SklearnIntentModel('tfidf_lr', lambda k: LogisticRegression(C=10, max_iter=2000, class_weight='balanced', random_state=42), select_k=None),
        'rf': lambda: SklearnIntentModel('tfidf_rf', lambda k: RandomForestClassifier(n_estimators=300, n_jobs=-1, class_weight='balanced_subsample', random_state=42)),
    }
    registry.update({
        'sgd': lambda: SklearnIntentModel('tfidf_sgd', lambda k: SGDClassifier(loss='modified_huber', alpha=1e-5, max_iter=50, class_weight='balanced', n_jobs=-1, random_state=42), select_k=None),
        'ridge': lambda: SklearnIntentModel('tfidf_ridge', lambda k: RidgeClassifier(alpha=1., class_weight='balanced'), select_k=None),
        'pa': lambda: SklearnIntentModel('tfidf_passive_aggressive', lambda k: PassiveAggressiveClassifier(C=.1, max_iter=50, n_jobs=-1, random_state=42), select_k=None),
        'cnb': lambda: SklearnIntentModel('tfidf_complement_nb', lambda k: ComplementNB(alpha=.3), select_k=None),
        'knn': lambda: SklearnIntentModel('tfidf_knn', lambda k: KNeighborsClassifier(n_neighbors=5, metric='cosine', weights='distance', n_jobs=-1), select_k=20000),
        'extratrees': lambda: SklearnIntentModel('tfidf_extratrees', lambda k: ExtraTreesClassifier(n_estimators=300, n_jobs=-1, class_weight='balanced_subsample', random_state=42)),
        'mlp': lambda: SklearnIntentModel('tfidf_mlp', lambda k: MLPClassifier(hidden_layer_sizes=(256,), early_stopping=True, max_iter=100, random_state=42), select_k=10000),
    })
    def xgb():
        from xgboost import XGBClassifier
        return SklearnIntentModel('tfidf_xgboost', lambda k: XGBClassifier(objective='multi:softprob', n_estimators=500, learning_rate=.1, max_depth=6, tree_method='hist', n_jobs=-1, early_stopping_rounds=30, random_state=42), early_stopping=True)
    def lgbm():
        from lightgbm import LGBMClassifier
        return SklearnIntentModel('tfidf_lightgbm', lambda k: LGBMClassifier(objective='multiclass', n_estimators=500, learning_rate=.1, num_leaves=63, random_state=42, verbosity=-1), early_stopping=True)
    registry.update({'xgboost': xgb, 'lightgbm': lgbm})
    return {n: registry[n]() for n in names}


def score(y, pred, labels):
    p, r, f, s = precision_recall_fscore_support(y, pred, labels=labels, zero_division=0)
    per_intent = pd.DataFrame({'intent': labels, 'precision': p, 'recall': r, 'f1': f, 'support': s})
    return {'accuracy': accuracy_score(y, pred), 'macro_f1': f1_score(y, pred, labels=labels, average='macro', zero_division=0)}, per_intent


def evaluate(predictions, tests, labels, slice_cols=('dtype', 'length', 'style')):
    """predictions: {model: array aligned with tests}. Returns overall, per-intent F1 and per-slice accuracy tables."""
    overall, per_intent, slices = [], {}, []
    for name, pred in predictions.items():
        pred = np.asarray(pred);m, pi = score(tests.intent, pred, labels)
        overall.append({'model': name, 'n': len(tests), **m, 'invalid_rate': float(np.mean(pred == 'invalid_llm_output'))})
        per_intent[name] = pi.set_index('intent').f1
        for col in slice_cols:
            if col not in tests:continue
            for value, idx in tests.groupby(col).groups.items():
                sub = tests.loc[idx]
                slices.append({'model': name, 'slice': col, 'value': value, 'n': len(sub), 'accuracy': accuracy_score(sub.intent, pred[tests.index.get_indexer(idx)]),
                               'macro_f1': f1_score(sub.intent, pred[tests.index.get_indexer(idx)], average='macro', zero_division=0)})
    support = tests.intent.value_counts().rename('support')
    per_intent = pd.DataFrame(per_intent).join(support).sort_values('support', ascending=False)
    return pd.DataFrame(overall).sort_values('macro_f1', ascending=False), per_intent, pd.DataFrame(slices)


def stratified_sample(tests, n, seed=42):
    """Cap the (paid, slow) LLM evaluation while keeping every intent and data type represented."""
    if n is None or n >= len(tests):return tests
    return pd.concat([g.sample(max(1, round(n * len(g) / len(tests))), random_state=seed) for _, g in tests.groupby(['intent', 'dtype'])])


def run(models=ALL_MODELS, llm_samples=500, use_llm=True, out=OUT):
    out = Path(out);out.mkdir(parents=True, exist_ok=True)
    train, val, tests = load_en_data();labels = sorted(train.intent.unique());preds, times = {}, {}
    for name, model in build_models(models).items():
        model.fit(train, val);preds[model.name] = model.predict(tests.text);times[model.name] = model.train_time_s
    sub = tests
    if use_llm:
        try:
            from .llm_classifier import LLMIntentClassifier
        except ImportError:
            from llm_classifier import LLMIntentClassifier
        sub = stratified_sample(tests, llm_samples)
        llm = LLMIntentClassifier(labels)
        preds = {k: pd.Series(v, index=tests.index).loc[sub.index].values for k, v in preds.items()}
        preds[f'llm_{llm.model}'] = llm.predict(sub.text)
    overall, per_intent, slices = evaluate(preds, sub, labels)
    overall['train_time_s'] = overall.model.map(times)
    overall.to_csv(out / 'overall.csv', index=False);per_intent.to_csv(out / 'per_intent_f1.csv');slices.to_csv(out / 'slices.csv', index=False)
    return overall, per_intent, slices, sub, preds


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--models', nargs='+', default=list(ALL_MODELS), choices=ALL_MODELS)
    ap.add_argument('--no-llm', action='store_true');ap.add_argument('--llm-samples', type=int, default=500)
    a = ap.parse_args()
    o, *_ = run(a.models, a.llm_samples, not a.no_llm)
    print(o.to_string(index=False))


def tune(key, grid, train, val, scoring='macro_f1'):
    """Grid-search one model's classifier params on the validation set; returns a DataFrame sorted best-first.
    grid example: {'C': [.1, .5, 1, 2]}. Test data is never touched."""
    import itertools
    rows = []
    for values in itertools.product(*grid.values()):
        params = dict(zip(grid, values));m = build_models([key])[key]
        base = m.make_clf;m.make_clf = lambda k, base=base, params=params: base(k).set_params(**params)
        m.fit(train, val);pred = m.predict(val.text);sc, _ = score(val.intent, pred, sorted(train.intent.unique()))
        rows.append({**params, **sc, 'train_time_s': m.train_time_s})
    return pd.DataFrame(rows).sort_values(scoring, ascending=False).reset_index(drop=True)
