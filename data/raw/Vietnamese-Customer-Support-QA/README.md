---
dataset_info:
  features:
  - name: question
    dtype: string
  - name: answer
    dtype: string
  - name: type
    dtype: string
  splits:
  - name: train
    num_bytes: 3018020
    num_examples: 8349
  - name: test
    num_bytes: 460981
    num_examples: 1500
  download_size: 1461517
  dataset_size: 3479001
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train-*
  - split: test
    path: data/test-*
pretty_name: CSConDa
license: cc-by-nc-4.0
language:
- vi
multilinguality: monolingual
size_categories:
- 1K<n<10K
source_datasets:
- original
task_categories:
- question-answering
- text-generation
- text-classification
task_ids:
- closed-domain-qa
annotations_creators:
- expert-generated
language_creators:
- found
tags:
- customer-support
- customer-service
- conversational-qa
- llm-evaluation
- benchmark
- vietnamese
extra_gated_heading: "Request access to CSConDa"
extra_gated_description: "Part of the CSConDa: Vietnamese Customer Support QA collection. The dataset contains anonymized real-world customer support conversations and is released for non-commercial research under CC BY-NC 4.0. Access is granted automatically once you submit this form."
extra_gated_prompt: "By requesting access, you agree to use CSConDa for non-commercial research only, not to redistribute it outside the terms of its license, not to attempt to re-identify any individual or organization in the data, and to cite the paper 'A Benchmark Dataset and Evaluation Framework for Vietnamese Large Language Models in Customer Support' (ICCCI 2025) in any work that uses it. Citing the paper is a condition of access."
extra_gated_fields:
  Full name: text
  Email: text
  Affiliation: text
  Organization type:
    type: select
    options:
    - University
    - Research institute
    - Company
    - Government or public sector
    - Non-profit organization
    - Independent researcher
  Country: country
  Position:
    type: select
    options:
    - Undergraduate student
    - Graduate student (Master's or PhD)
    - Postdoctoral researcher
    - Faculty or professor
    - Research scientist or engineer
    - Industry practitioner
    - Government or public sector staff
    - label: Other
      value: other
  Intended use:
    type: select
    options:
    - Academic research
    - Thesis or coursework
    - Teaching
    - Benchmarking or evaluation
    - Model training or fine-tuning
    - Non-commercial prototyping
    - label: Other
      value: other
  Briefly describe how you plan to use the dataset: text
  I agree to use this dataset for non-commercial research purposes only: checkbox
  I agree not to redistribute this dataset outside the terms of its license: checkbox
  I agree not to attempt to re-identify any individual or organization in this dataset: checkbox
  I agree to cite the CSConDa paper in any work that uses this dataset: checkbox
extra_gated_button_content: "Agree and access"
---

# CSConDa: Customer Support Conversations Dataset for Vietnamese

**CSConDa** is the first Vietnamese question answering dataset in the **customer support** domain. It contains **over 9,000 QA pairs** curated from real interactions between customers and human advisors. The data was collected and approved in collaboration with [DooPage](https://doopage.com/), a Vietnamese software company that serves 30,000 customers and 45,000 advisors through its multi-channel support platform.

The questions cover a wide range of service topics, from pricing inquiries and product availability to technical troubleshooting. They keep the informal style of real customer messages: abbreviations, typos, missing diacritics and code-switching. This makes CSConDa a realistic benchmark for Vietnamese LLMs in customer-facing applications.

**Paper:** Long S. T. Nguyen, Truong P. Hua, Thanh M. Nguyen, Toan Q. Pham, Nam K. Ngo, An X. Nguyen, Nghi D. M. Pham, Nghia H. Nguyen, and Tho T. Quan. *A Benchmark Dataset and Evaluation Framework for Vietnamese Large Language Models in Customer Support.* International Conference on Computational Collective Intelligence (ICCCI), 2025. [[Website]](https://link.springer.com/chapter/10.1007/978-3-032-10202-7_33)

> <div><b>TL;DR:</b> CSConDa contains 9,849 Vietnamese QA pairs from real customer–advisor conversations, each labeled with its question type. Benchmarking 11 open-source Vietnamese LLMs (7–9B) shows that Vistral 7B performs best overall, while all models give noticeably more verbose answers than human advisors.</div>

> <div><b>Part of a collection:</b> CSConDa is featured in the <a href="https://huggingface.co/collections/longstnguyen/csconda-vietnamese-customer-support-qa">CSConDa: Vietnamese Customer Support QA collection</a> on Hugging Face.</div>
> <br>
> <div><b>Citation required:</b> Access is granted on the condition that any work using this dataset cites the paper. See the <a href="#9-citation">BibTeX entry</a> below.</div>

## 1. Dataset at a glance

CSConDa captures authentic customer support exchanges, summarized below:

| Property | Value |
|---|---|
| QA pairs | 9,849 (train 8,349 · test 1,500) |
| Source | Real customer–advisor conversations (DooPage) |
| Question types | General, Domain-Specific Simple, Domain-Specific Complex |
| Privacy | Personal and sensitive information is masked |
| Language | Vietnamese (informal, conversational) |

## 2. Usage

CSConDa is a gated dataset. Before loading it:

- Open this page while signed in to Hugging Face and submit the access form. Access is granted immediately.
- Authenticate locally with `hf auth login`, or pass `token=...` to `load_dataset`.

Once access is granted, the dataset can be loaded with the `datasets` library:

```python
from datasets import load_dataset

ds = load_dataset("ura-hcmut/Vietnamese-Customer-Support-QA")   # train / test

sample = ds["test"][0]
print(sample["question"])
print(sample["answer"])
print(sample["type"])
```

## 3. Data fields

Each record is a single customer message paired with the advisor's reply:

| Field | Type | Description |
|---|---|---|
| `question` | string | Customer message, kept in its original informal style |
| `answer` | string | Response written by a human support advisor |
| `type` | string | Question type: `General`, `Domain - Specific Simple` or `Domain - Specific Complex` |

**Example:** a customer asks why Shopee orders do not appear in the chat view.

```json
{
  "question": "phần chat trên page với shopê. ko nhìn thấy được đơn hàng khách đặt. có cách nào nhìn thấy kiểu khách đặt gì ko a.",
  "answer": "dạ hiện tại phần thông tin này shopee chưa truyền cho phần mềm ạ..",
  "type": "Domain - Specific Simple"
}
```

**Privacy:** names, phone numbers, emails, addresses, links and brand names are replaced with placeholders such as `<tên>`, `<sđt>`, `<email>`, `<địa chỉ>`, `<liên kết>` and `<thương hiệu>`.

## 4. Question types

Each pair is annotated with one of three question types, following expert-guided guidelines:

| Type | Definition | Characteristics | Example |
|---|---|---|---|
| General | Common conversational phrases unrelated to a specific topic, such as greetings, farewells or brief acknowledgments. | Short, with minimal semantic content and generic wording. | âu kê thank kiu e. *(Okay, thank you.)* |
| Domain-Specific Simple | Direct, fact-based questions that need a concise answer. | Concise, less dependent on context, often mentions service terms such as "Doopage", "chatbot" or "Zalo". | Báo giá giúp M nhé. Gọi M lúc 11h số này nef \<số điện thoại\>. C cần qly 8 page, 2 Zalo, 1 website, 1 YTB, 3-5 người dùng. *(Please send me the pricing details. Call me at 11 AM at this number \<phone number\>. I need 8 pages, 2 Zalo accounts, 1 website and 1 YouTube channel for 3–5 users.)* |
| Domain-Specific Complex | Questions that need detailed explanations, often troubleshooting with multiple steps. | Longer, with problem descriptions, error messages and technical terms. | à thế đây là teen maps. chứ đâu phải tên business đâu em. tên 1 địa chỉ map đó. Nhưng lsao mà gõ tên map vào đó được. trong khi bên trong cho phép add nhiều locations? Lỗi file này e ơi, ko down đc. Bên Zalo OA down bt. *(Oh, so this is the name on Google Maps, not the business name. How can I enter a map name when multiple locations are allowed? This file is corrupted and cannot be downloaded. On Zalo OA, the download works fine.)* |

## 5. Splits and statistics

The train split follows the natural distribution of the conversations, while the test split is balanced across question types:

| Type | Train | Test | All |
|---|---:|---:|---:|
| General | 3,023 | 500 | 3,523 |
| Domain-Specific Simple | 4,712 | 500 | 5,212 |
| Domain-Specific Complex | 614 | 500 | 1,114 |
| **Total** | **8,349** | **1,500** | **9,849** |

With 500 questions per type, the test split supports a fair per-type comparison of models.

**Average length:** test questions are longer on average, whereas training answers are longer (values in characters).

| | Train | Test |
|---|---:|---:|
| Question | 70.5 | 85.5 |
| Answer | 185.8 | 127.1 |

## 6. Benchmark results

The paper benchmarks 11 lightweight open-source Vietnamese LLMs (7–9B parameters) on the CSConDa test split, combining automatic metrics with hallucination detection and an in-depth syntactic analysis of the generated answers. Its main findings are:

- **Best models:** Vistral 7B achieves the strongest overall results, followed by SeaLLMs 7B, Sailor 7B, SEA-LION 7B and GemSUra 7B.
- **Vietnamese-specific vs. multilingual models:** there is no significant performance gap between models fine-tuned for Vietnamese and multilingual models that support Vietnamese.
- **Writing style:** semantic similarity (BERTScore) stays acceptable, but lexical metrics are much lower, showing that models express similar meaning in wording that differs from how human advisors write.
- **Verbosity:** models produce longer, structurally inflated answers than human advisors, which is associated with semantic drift and hallucination.

See the paper for the full results per question type.

## 7. Intended use and limitations

CSConDa is built from real conversations, so please keep the following points in mind:

- **Intended use:** benchmarking and fine-tuning Vietnamese LLMs for customer support, and classifying the type of a customer question. The balanced `test` split supports fair per-type comparisons, and the `train` split supports domain adaptation.
- **Privacy:** personal and sensitive information is masked with placeholders, and users must not attempt to re-identify any individual or organization in the data.

## 8. License

Released under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) for non-commercial research, consistent with the license stated in the ViRE paper. Users must not attempt to re-identify any individual or organization in the data.

## 9. Citation

If you use CSConDa, please cite:

```bibtex
@inproceedings{10.1007/978-3-032-10202-7_33,
  title     = {A Benchmark Dataset and Evaluation Framework for Vietnamese Large Language Models in Customer Support},
  author    = {Nguyen, Long S. T. and Hua, Truong P. and Nguyen, Thanh M. and Pham, Toan Q. and Ngo, Nam K. and Nguyen, An X. and Pham, Nghi D. M. and Nguyen, Nghia H. and Quan, Tho T.},
  editor    = {Nguyen, Ngoc Thanh and Dinh Duc Anh, Vu and Kozierkiewicz, Adrianna and Nguyen Van, Sinh and Nunez, Manuel and Treur, Jan and Vossen, Gottfried},
  booktitle = {Advances in Computational Collective Intelligence},
  year      = {2026},
  publisher = {Springer Nature Switzerland},
  address   = {Cham},
  pages     = {481--496},
  isbn      = {978-3-032-10202-7}
}
```

## 10. Contact

For questions, issues or feedback, please contact **Long S. T. Nguyen** ([long.nguyencse2023@hcmut.edu.vn](mailto:long.nguyencse2023@hcmut.edu.vn)), URA Research Group, Faculty of Computer Science and Engineering, Ho Chi Minh City University of Technology (HCMUT), VNU-HCM.
