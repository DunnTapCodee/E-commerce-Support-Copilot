# Module 1 — bilingual NLU

This delivery contains code and unexecuted Kaggle notebooks. Training, dataset
translation, QC, measurements and tests have **not** been run. No model is claimed
to be selected and no evaluation numbers are supplied. The API reports `degraded`
until real artifacts and a fitted router exist. The 12 operational intent names
and the existing response fields are preserved.

Run all commands from the repository root. Python 3.11 is recommended.

## Local installation and artifacts

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-train.txt
```

Serving sklearn is pinned to 1.6.1, matching the local environment inspected before
this update. Each training run records the installed version; loading refuses a
mismatch. If another local version is required, pin that exact version in both
training and the serving image and retrain. Do not load Kaggle sklearn pickles.
Heavy model operations are implemented only in Kaggle notebooks.

Legacy English artifacts were moved to `artifacts/models/legacy_linearsvc_en/`.
They are never auto-loaded. Seed examples in `pipeline/dataset.py` are smoke data
only. The legacy baseline report is intentionally absent because this delivery
does not execute inference measurements. Its optional generator is
`python -m services.intent_service.src.pipeline.experiments.legacy_baseline`.

## Data, translation and QC (in dependency order)

```bash
python -m services.intent_service.src.pipeline.data.build_datasets inspect-qa
python -m services.intent_service.src.pipeline.data.build_datasets prepare
python kaggle/configure.py --username YOUR_KAGGLE_USERNAME --stage data/interim/translation_input.parquet
```

`prepare` downloads Bitext and CLINC OOS, excludes Bitext responses, prints label
counts, discovers every placeholder, writes `reports/module1/placeholders.json`,
and stops on unknown placeholder names so their value types can be mapped explicitly.
Sources are split by `group_id` before augmentation. Exact duplicates share one
translation request and are joined back by `translation_join.parquet`.

QA augmentation is optional and never chosen from type names automatically. Inspect
types and examples first. To enable reviewed non-commerce types, pass
`--qa-selection path/to/reviewed_types.json` to `prepare`, where the JSON maps each
selected type to its written reason. An obsolete optional QA intermediate is removed when `prepare` is rerun without that selection. OOS is capped separately and is intentionally
not downsampled to match the Bitext balancing ratio.

Authenticate Kaggle yourself with `~/.kaggle/kaggle.json` (mode 600), or
`KAGGLE_USERNAME`/`KAGGLE_KEY`. GPU and Internet require a verified account. Code
never searches for credentials or uploads data automatically. Generated metadata
uses the visible placeholder `KUSER` until `configure.py` is run with your username.

```bash
kaggle datasets create -p kaggle/datasets/ecom-intent-data --dir-mode zip
kaggle kernels push -p kaggle/kernels/k01-translate-en2vi
kaggle kernels status YOUR_KAGGLE_USERNAME/k01-translate-en2vi
kaggle kernels output YOUR_KAGGLE_USERNAME/k01-translate-en2vi -p kaggle/output/k01
```

Poll status manually no more frequently than every 5–10 minutes. Dataset metadata
is private and contains the `other` license marker; retain the source license.
No kernel has been pushed, so there are no successful kernel URLs to report.

To keep each kernel below six hours, k01 translates with beam search and k02 samples
paraphrases **only for train rows**:

```bash
python kaggle/configure.py --username YOUR_KAGGLE_USERNAME --stage kaggle/output/k01/bitext_vi_translated.parquet
kaggle datasets version -p kaggle/datasets/ecom-intent-data -m "Base translations" --dir-mode zip
kaggle kernels push -p kaggle/kernels/k02-paraphrase-vi
kaggle kernels status YOUR_KAGGLE_USERNAME/k02-paraphrase-vi
kaggle kernels output YOUR_KAGGLE_USERNAME/k02-paraphrase-vi -p kaggle/output/k02
python -m services.intent_service.src.pipeline.data.build_datasets qc-pairs --translated kaggle/output/k02/bitext_vi_translated.parquet
python kaggle/configure.py --username YOUR_KAGGLE_USERNAME --stage data/interim/qc_pairs.parquet
kaggle datasets version -p kaggle/datasets/ecom-intent-data -m "Translation QC pairs" --dir-mode zip
kaggle kernels push -p kaggle/kernels/k03-embed-minilm
kaggle kernels status YOUR_KAGGLE_USERNAME/k03-embed-minilm
kaggle kernels output YOUR_KAGGLE_USERNAME/k03-embed-minilm -p kaggle/output/k03-qc
python -m services.intent_service.src.pipeline.data.qc_translation --cosines kaggle/output/k03-qc/qc_cos.npy
python -m services.intent_service.src.pipeline.data.build_datasets finalize
```

QC runs semantic encoding on Kaggle rather than estimating a long CPU job locally.
Candidates with missing/duplicated slots, suspicious length, untranslated English or
cosine < .70 are rejected. Paraphrases require their own QC. The QC command exits
with an error if fewer than 95% of source rows survive recovery or any Bitext intent
has fewer than 800 VI rows. Review the report before proceeding.

Fill `data/eval/real_vi_handwritten.csv` with **200–300 independently written real
queries**. It is delivered as a header-only template. An empty file is skipped and
reported; no real queries are invented. Existing benchmark scenarios remain an
additional evaluation set. `warranty` is mapped to `out_of_scope`.

Translation/paraphrase checkpoints are emitted in `/kaggle/working`. To resume a
new session, download the partial parquet, stage it in the private dataset and
version it before rerunning. For fine-tuning, stage the prior `A1-phobert`/`A1-roberta`/`A1-distilroberta` directory containing `checkpoints/` in the private dataset; the notebook restores it automatically. Three failures with the same cause
require human investigation; scripts do not push retry kernels automatically.

## Router, experiments and final embedding pass

```bash
python -m services.intent_service.src.router
python -m services.intent_service.src.pipeline.experiments.run_baselines --lang vi
python -m services.intent_service.src.pipeline.experiments.run_baselines --lang en
```

B1 compares LR and calibrated LinearSVC on word/character TF-IDF. B2 includes RF,
LightGBM and SVD+MLP. Calibration folds keep augmented siblings in the same group.
Validation selects hyperparameters and confidence thresholds; test data never
selects thresholds. `threshold=null` means no cutoff achieved 95% accepted accuracy
and makes that run ineligible for deployment.

Upload processed parquet files to the private dataset using `configure.py --stage`
(the command accepts multiple file paths), then version the dataset. Run k03 again
for A2 embeddings, followed by k04 and k05 for transformer experiments:

```bash
python kaggle/configure.py --username YOUR_KAGGLE_USERNAME --stage data/processed/module1/*.parquet
kaggle datasets version -p kaggle/datasets/ecom-intent-data -m "Final bilingual splits" --dir-mode zip
kaggle kernels push -p kaggle/kernels/k03-embed-minilm
kaggle kernels status YOUR_KAGGLE_USERNAME/k03-embed-minilm
kaggle kernels output YOUR_KAGGLE_USERNAME/k03-embed-minilm -p kaggle/output/k03
python -m services.intent_service.src.pipeline.experiments.train_embed_lr --embeddings kaggle/output/k03
kaggle kernels push -p kaggle/kernels/k04-finetune-phobert
kaggle kernels status YOUR_KAGGLE_USERNAME/k04-finetune-phobert
kaggle kernels output YOUR_KAGGLE_USERNAME/k04-finetune-phobert -p kaggle/output/k04
kaggle kernels push -p kaggle/kernels/k05-finetune-roberta-en
kaggle kernels status YOUR_KAGGLE_USERNAME/k05-finetune-roberta-en
kaggle kernels output YOUR_KAGGLE_USERNAME/k05-finetune-roberta-en -p kaggle/output/k05
python -m services.intent_service.src.pipeline.experiments.import_transformer --source kaggle/output/k04/A1-phobert
python -m services.intent_service.src.pipeline.experiments.import_transformer --source kaggle/output/k05/A1-roberta
python -m services.intent_service.src.pipeline.experiments.import_transformer --source kaggle/output/k05/A1-distilroberta
```

A2 uses one multilingual LR and does not route model inference. A1 uses identical
shared NFC/lowercase preprocessing, plus PyVi for PhoBERT in both training and
serving. The importer confirms local/Kaggle evaluation row alignment and refuses
ONNX models whose Macro-F1 drops more than one point from the GPU reference.
No transformer export or embedding job runs on local CPU.

All notebooks are standalone and are generated from readable `kaggle/jobs/*.py`;
regenerate them after editing those sources. Fine-tuning uses a 5.25-hour stop
callback; incomplete training saves a checkpoint and refuses final export.

## Local latency, selection and deployment

```bash
python -m services.intent_service.src.pipeline.experiments.benchmark_latency
python -m services.intent_service.src.pipeline.experiments.summarize
python -m services.intent_service.src.pipeline.experiments.deploy
```

Latency is local CPU, batch one, 50 warmups and 500 measured queries, including
preprocessing, language detection, segmentation, tokenizer, model and label
selection. Worker subprocesses isolate single-thread and default-thread modes.
For a language-specific artifact this measures the specified backend on the same
mixed held-out corpus; it does not pretend to load its counterpart. Selection
requires eligible VI and EN runs or a multilingual run. The comparison report
states the latency admission rule explicitly.

Deployment copies artifacts into `intent/vi`, `intent/en`, or `intent/multi` and
writes `artifacts/models/intent/deployment.env`. Source this file after `.env` for
local launch, or pass it as a Compose env file. The gateway uses the conservative
maximum of the selected language cutoffs, preserving its other guardrail logic.
Existing destination model directories are not overwritten automatically.

```bash
set -a
source .env
source artifacts/models/intent/deployment.env
set +a
python run_dev.py
# Alternative:
docker compose --env-file .env --env-file artifacts/models/intent/deployment.env up --build
```

`run_dev.py` reads `.env`; Module 1 also loads the generated deployment env after
it. `/health` exposes routing mode, loaded models and an explicit load error.
Artifacts, datasets, credentials and generated metrics are ignored by Git.
There are no test commands in this delivery workflow, per the code-only request.
