"""
Generate text-to-image molecule dataset.

This script generates a dataset for training text-to-image models:
- Input: Compound names (Records Name) and SMILES
- Output: Molecule structure images with text prompts

Usage:
    python generate_dataset.py --input compounds.xlsx --output-dir ./output

    # With row range
    python generate_dataset.py --input compounds.xlsx --output-dir ./output \
        --start 70000 --limit 40000

Output structure:
    output/
    ├── answers/*.png           # Molecule structure images
    └── metadata.jsonl          # Text prompts and image paths
"""

import os
import sys
import json
import random
import argparse
from pathlib import Path

import pandas as pd
from PIL import Image
import io
from tqdm import tqdm

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "common"))
from utils import smiles_to_mol
from rendering import draw_molecule


# Prompt templates for text generation
PROMPT_TEMPLATES = [
    "Draw the 2D skeletal structure of {name}. Strictly generate the molecule based on the provided substance names, paying close attention to the insertion points and structural integrity of the substructures. Use standard conventions for element coloring (e.g., blue for nitrogen, red for oxygen, yellow for sulfur, orange for phosphorus).",
    "Generate a clean 2D molecular structure diagram of {name}. Ensure the skeletal structure accurately represents the connectivity and stereochemistry. Use standard element coloring conventions: (e.g., blue for nitrogen, red for oxygen, yellow for sulfur, orange for phosphorus).",
    "Create a scientific illustration of {name} showing its 2D skeletal formula. The drawing should be precise, following standard chemical drawing conventions. Use standard conventions for element coloring (e.g., blue for nitrogen, red for oxygen, yellow for sulfur, orange for phosphorus).",
    "Depict the molecular structure of {name} using standard skeletal notation. Maintain strict accuracy in bond connectivity and ring structures. Use standard conventions for element coloring (e.g., blue for nitrogen, red for oxygen, yellow for sulfur, orange for phosphorus).",
]

DEFAULT_PROMPT = (
    "Draw the 2D skeletal structure of the molecule. Strictly generate the molecule "
    "based on the provided substance names, paying close attention to the insertion points "
    "and structural integrity of the substructures. Use standard conventions for element "
    "coloring (e.g., blue for nitrogen, red for oxygen, yellow for sulfur, orange for phosphorus)."
)


def build_prompt(records_name: str) -> str:
    """
    Build a text prompt from compound name.
    
    Args:
        records_name: Compound name
    
    Returns:
        Text prompt for image generation
    """
    if not records_name or pd.isna(records_name):
        return DEFAULT_PROMPT
    
    name = str(records_name).strip()
    return random.choice(PROMPT_TEMPLATES).format(name=name)


def generate_dataset(
    input_file: str,
    output_dir: str,
    img_size: tuple = (512, 512),
    start: int = 0,
    limit: int = None,
):
    """
    Generate text-to-image molecule dataset.
    
    Args:
        input_file: Input Excel/CSV file with SMILES and Records Name
        output_dir: Output directory
        img_size: Image size (width, height)
        start: Starting row index
        limit: Maximum number of rows to process
    """
    output_dir = Path(output_dir)
    answers_dir = output_dir / "answers"
    answers_dir.mkdir(parents=True, exist_ok=True)
    
    # Load data
    print(f"Loading data from: {input_file}")
    
    if input_file.endswith('.xlsx'):
        df = pd.read_excel(input_file)
    else:
        df = pd.read_csv(input_file)
    
    # Apply row range
    if start > 0:
        df = df.iloc[start:]
    if limit:
        df = df.head(limit)
    
    print(f"Processing rows: {start} to {start + len(df)}")
    
    # Find columns
    smile_col = None
    for col in ['Smiles', 'Smile', 'smiles', 'smile']:
        if col in df.columns:
            smile_col = col
            break
    
    name_col = None
    for col in ['Records Name', 'Name', 'name', 'Compound Name']:
        if col in df.columns:
            name_col = col
            break
    
    if smile_col is None:
        raise ValueError(f"Could not find SMILES column. Available: {df.columns.tolist()}")
    
    print(f"SMILES column: {smile_col}")
    if name_col:
        print(f"Name column: {name_col}")
    
    smiles_list = df[smile_col].dropna().tolist()
    names_list = df[name_col].tolist() if name_col else [None] * len(df)
    
    metadata = []
    generated = 0
    errors = 0
    
    for i, (smiles, name) in enumerate(tqdm(zip(smiles_list, names_list), total=len(smiles_list))):
        mol = smiles_to_mol(smiles)
        
        if mol is None:
            errors += 1
            continue
        
        try:
            # Generate image
            img = draw_molecule(
                mol,
                size=img_size,
                style_key="rdkit_color",
                add_annotation=True
            )
            
            if img is None:
                errors += 1
                continue
            
            # Save image
            img_id = i  # Use index from processed range
            img_filename = f"{img_id}.png"
            img_path = answers_dir / img_filename
            img.save(img_path)
            
            # Build prompt
            prompt = build_prompt(name)
            
            # Metadata entry
            entry = {
                "id": img_id,
                "image": [f"answers/{img_filename}"],
                "conversations": [
                    {"from": "human", "value": prompt},
                    {"from": "gpt", "value": "<image>"}
                ],
                "width": [img_size[0]],
                "height": [img_size[1]],
                "generation_flags": 1,
            }
            
            # Add optional fields
            if name:
                entry["compound_name"] = str(name)
            entry["smiles"] = smiles
            
            metadata.append(entry)
            generated += 1
            
        except Exception as e:
            errors += 1
            continue
    
    # Save metadata
    metadata_path = output_dir / "metadata.jsonl"
    with open(metadata_path, "w", encoding="utf-8") as f:
        for entry in metadata:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    print(f"\nGeneration complete!")
    print(f"Successfully generated: {generated}")
    print(f"Errors: {errors}")
    print(f"Output directory: {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate text-to-image molecule dataset"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input Excel/CSV file with SMILES and compound names"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./output",
        help="Output directory"
    )
    parser.add_argument(
        "--img-size",
        type=int,
        nargs=2,
        default=[512, 512],
        help="Image size (width height)"
    )
    parser.add_argument(
        "--start", "-s",
        type=int,
        default=0,
        help="Starting row index"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=None,
        help="Limit number of rows to process"
    )
    
    args = parser.parse_args()
    
    img_size = tuple(args.img_size) if isinstance(args.img_size, list) else (args.img_size, args.img_size)
    
    generate_dataset(
        args.input,
        args.output_dir,
        img_size,
        args.start,
        args.limit
    )


if __name__ == "__main__":
    main()
