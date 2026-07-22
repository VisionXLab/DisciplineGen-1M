# Chemical Data Pipeline

Lightweight scripts for building multimodal chemistry datasets from SMILES or reaction data. The repository currently includes three pipelines:

- `01_molecule_editing`: original molecule to highlighted question image plus edited answer image
- `02_reaction_editing`: reactant-side question image plus complete reaction answer image
- `03_molecule_t2i`: text prompt plus 2D molecule structure image

## Installation

Install dependencies with:

```bash
pip install -r common/requirements.txt
```

Optional:

- `epam-indigo` can be installed if Indigo rendering is needed.

## Repository Layout

```text
open-source/
├── common/
│   ├── utils.py
│   ├── rendering.py
│   └── requirements.txt
├── pipelines/
│   ├── 01_molecule_editing/
│   ├── 02_reaction_editing/
│   └── 03_molecule_t2i/
└── README.md
```

## Pipelines

### 1. Molecule Editing

Input: compound table with a SMILES column.

Typical flow:

```bash
python pipelines/01_molecule_editing/preprocess/filter_compounds.py \
    --input compounds.xlsx \
    --output filtered_compounds.xlsx

python pipelines/01_molecule_editing/generate_dataset.py \
    --input filtered_compounds.xlsx \
    --output-dir ./molecule_editing_output

python pipelines/01_molecule_editing/convert_to_jsonl.py \
    --input ./molecule_editing_output/metadata.jsonl \
    --questions-dir ./molecule_editing_output/questions \
    --answers-dir ./molecule_editing_output/answers \
    --output ./molecule_editing_output/annotations.jsonl
```

### 2. Reaction Editing

Input: reaction CSV with reaction SMILES and confidence fields.

Typical flow:

```bash
python pipelines/02_reaction_editing/preprocess/filter_reactions.py \
    --input reactions.csv \
    --output filtered_reactions.csv

python pipelines/02_reaction_editing/preprocess/split_reactions.py \
    --csv filtered_reactions.csv \
    --output split_reactions.csv \
    --reaction-column ReactionSmiles

python pipelines/02_reaction_editing/generate_dataset.py \
    --input split_reactions.csv \
    --output-dir ./reaction_output \
    --style rdkit_color

python pipelines/02_reaction_editing/convert_to_jsonl.py \
    --input ./reaction_output/qa_pairs.json \
    --questions-dir ./reaction_output/questions \
    --answers-dir ./reaction_output/answers \
    --output ./reaction_output/annotations.jsonl
```

### 3. Molecule Text to Image

Input: compound table with SMILES and optional compound names.

Typical flow:

```bash
python pipelines/03_molecule_t2i/preprocess/filter_compounds.py \
    --input compounds.xlsx \
    --output filtered_compounds.xlsx \
    --start 0 \
    --limit 10000

python pipelines/03_molecule_t2i/generate_dataset.py \
    --input filtered_compounds.xlsx \
    --output-dir ./t2i_output \
    --img-size 512 512

python pipelines/03_molecule_t2i/convert_to_jsonl.py \
    --input ./t2i_output/metadata.jsonl \
    --answers-dir ./t2i_output/answers \
    --output ./t2i_output/annotations.jsonl
```

## Output Format

All pipelines ultimately produce training JSONL records in a shared structure:

```json
{
    "id": 0,
    "image": ["questions/0.png", "answers/0.png"],
    "conversations": [
        {"from": "human", "value": "<image>\n..."},
        {"from": "gpt", "value": "<image>"}
    ],
    "width": [512, 512],
    "height": [512, 512],
    "generation_flags": [0, 1]
}
```

## Data Sources

- USPTO-50K reaction data: [pingzhili/uspto-50k · Datasets at Hugging Face](https://huggingface.co/datasets/pingzhili/uspto-50k)
- ChEMBL compound data: [Explore all Compounds - ChEMBL](https://www.ebi.ac.uk/chembl/explore/compounds/)

## Notes

- This repository contains processing scripts only. Raw source datasets are not distributed here and should be obtained from their original providers.
- Input tables must provide the columns expected by each pipeline, such as SMILES fields and reaction columns.
