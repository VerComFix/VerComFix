
# VerComFix

## 1 Description

`VerComFix` aims to address Incompatible Third-party Library API Usage issues in LLM code completion.

It provides a large-scale benchmark comprised of real-world code completion tasks, and a versioned TPL API Knowledge based framework for more compatibility-aware code generation .

## 2 Usage

### 2.1 Environment Setup

```bash
# clone this repo
git clone https://github.com/JZuming/TxCheck.git

cd VerComFix
conda env create -f environment.yml # init conda environment
conda activate vercomfix            # activate conda environment
```

### 2.2 Data Preparation

```bash
cd data_collection

# 1. Repository Selection & Download
python select_repo.py
python download_repo.py

# 2. PyPI Package Collection
python get_top_package_name_from_Libraries.py
python craw_package_from_PyPI.py
python uncompress_package.py
```

### 2.3 Knowledge Base Construction

```bash
cd knowledge_builder

# init db
python db.py

# collect API signature knowledge
python get_top_level_from_package.py
python sniffer_thread.py
```

### 2.4 Task Construction

```bash
cd task_construction

# init db
python db.py

# construct API-Level & Function-Level Task
python extract_all.py
```

### 2.5 Code Completion

```bash
cd code_completion

python complete.py -m [Model_Name] [-f] [-o] [-g 0]
python eval.py -m [Model_Name] [-f]
```
### 2.6 Lightweight Repairment

```bash
cd lightweight_repair

python repair.py -m [Model_Name] [-g 0]
python eval.py -m [Model_Name]
```

### 3 Supported Options

| Option | Required | Description |
| :----- | :-:      | :--         |
| `-m, --model` | True | Language Model to use:<br> codegen-6b, starcoder2-7b, codellama-7b-instruct, deepseek-coder-6.7b, deepseek_r1_distill, gpt-4o |
| `-f, --func` | False | API_Level Task / Function-Level Task|
| `-o, --omit` | False | Omit Version Info in prompt |
| `-g, -gpu` | False | Index of GPU device|