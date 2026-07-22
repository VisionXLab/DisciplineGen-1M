"""
Generate reaction editing dataset.

This script generates QA image pairs for reaction prediction/editing task:
- Question: Reactant molecules (left side of reaction)
- Answer: Complete reaction (reactants >> products)

Supports multiple rendering styles:
- RDKit black and white
- RDKit color
- Indigo color

Usage:
    # Generate with default RDKit color style
    python generate_dataset.py --input reactions.csv --output-dir ./output
    
    # Generate with specific style
    python generate_dataset.py --input reactions.csv --output-dir ./output --style rdkit_bw
    
    # Generate with row range (for parallel processing)
    python generate_dataset.py --input reactions.csv --output-dir ./output --start 0 --end 10000

Output structure:
    output/
    ├── questions/*.png      # Reactant molecules
    ├── answers/*.png        # Complete reactions
    ├── qa_pairs.json       # QA metadata
    └── annotations.jsonl    # Standard training format
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Optional

import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from rdkit import Chem
from rdkit.Chem import rdChemReactions, rdMolDraw2D
from tqdm import tqdm
import io

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "common"))
from utils import normalize_reaction_smiles, smiles_to_mol


# Rendering styles configuration
RENDERING_STYLES = {
    "rdkit_bw": {
        "bg_color": (255, 255, 255),
        "use_bw_palette": True,
        "line_width": 2,
    },
    "rdkit_color": {
        "bg_color": (255, 255, 255),
        "use_bw_palette": False,
        "line_width": 2,
    },
    "indigo": {
        "renderer": "indigo",
        "bg_color": (255, 255, 255),
    },
}

DEFAULT_STYLE = "rdkit_color"


def draw_molecule_style(
    mol,
    size: int = 512,
    style: dict = None,
    add_text: str = None
) -> Image.Image:
    """
    Draw a molecule with specified style.
    
    Args:
        mol: RDKit Mol object
        size: Image size
        style: Style configuration dict
        add_text: Optional text to add below the molecule
    
    Returns:
        PIL Image
    """
    if mol is None:
        return None
    
    if style is None:
        style = RENDERING_STYLES["rdkit_color"]
    
    # Create drawer
    d2d = rdMolDraw2D.MolDraw2DCairo(size, size)
    opts = d2d.drawOptions()
    
    # Apply style
    bg_color = style.get("bg_color", (255, 255, 255))
    opts.bgColor = f"rgba({bg_color[0]},{bg_color[1]},{bg_color[2]},255)"
    opts.lineWidth = style.get("line_width", 2)
    
    if style.get("use_bw_palette"):
        opts.useBWAtomPalette()
    
    # Draw molecule
    d2d.DrawMolecule(mol)
    d2d.FinishDrawing()
    
    png_data = d2d.GetDrawingText()
    img = Image.open(io.BytesIO(png_data))
    
    if img.mode != "RGB":
        img = img.convert("RGB")
    
    # Add optional text
    if add_text:
        img = add_text_to_image(img, add_text)
    
    return img


def draw_reaction_style(
    reaction_smiles: str,
    size: int = 512,
    style: dict = None
) -> Optional[Image.Image]:
    """
    Draw a complete reaction with specified style.
    
    Args:
        reaction_smiles: Reaction SMILES string
        size: Image size
        style: Style configuration dict
    
    Returns:
        PIL Image or None if rendering fails
    """
    try:
        rxn = rdChemReactions.ReactionFromSmarts(reaction_smiles)
        if rxn is None:
            return None
        
        if style is None:
            style = RENDERING_STYLES["rdkit_color"]
        
        d2d = rdMolDraw2D.MolDraw2DCairo(size, size)
        opts = d2d.drawOptions()
        
        bg_color = style.get("bg_color", (255, 255, 255))
        opts.bgColor = f"rgba({bg_color[0]},{bg_color[1]},{bg_color[2]},255)"
        
        if style.get("use_bw_palette"):
            opts.useBWAtomPalette()
        
        d2d.DrawReaction(rxn, highlightByReactants=True)
        d2d.FinishDrawing()
        
        png_data = d2d.GetDrawingText()
        img = Image.open(io.BytesIO(png_data))
        
        if img.mode != "RGB":
            img = img.convert("RGB")
        
        return img
    except Exception:
        return None


def add_text_to_image(img: Image.Image, text: str, font_size: int = 20) -> Image.Image:
    """Add text annotation below the molecule."""
    width, height = img.size
    text_height = 60
    
    new_img = Image.new("RGB", (width, height + text_height), color=(255, 255, 255))
    new_img.paste(img, (0, 0))
    
    draw = ImageDraw.Draw(new_img)
    
    # Try to use a font, fallback to default
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()
    
    # Draw text
    text_x = 10
    text_y = height + 10
    draw.text((text_x, text_y), text, fill=(0, 0, 0), font=font)
    
    return new_img


def extract_reactants(reaction_smiles: str) -> str:
    """Extract reactants portion from reaction SMILES."""
    if not reaction_smiles:
        return ""
    
    if ">>" in reaction_smiles:
        return reaction_smiles.split(">>")[0] + ">>"
    
    if ">" in reaction_smiles:
        parts = reaction_smiles.split(">")
        return ".".join(parts[:-1]) + ">>"
    
    return reaction_smiles


def generate_dataset(
    input_csv: str,
    output_dir: str,
    style_key: str = "rdkit_color",
    img_size: int = 512,
    start: int = 0,
    end: Optional[int] = None,
    limit: Optional[int] = None,
    prompt_template: str = None
):
    """
    Generate reaction editing dataset.
    
    Args:
        input_csv: Input CSV file path
        output_dir: Output directory
        style_key: Rendering style key
        img_size: Image size
        start: Starting row index
        end: Ending row index (exclusive)
        limit: Limit number of rows
        prompt_template: Custom prompt template
    """
    output_dir = Path(output_dir)
    questions_dir = output_dir / "questions"
    answers_dir = output_dir / "answers"
    
    questions_dir.mkdir(parents=True, exist_ok=True)
    answers_dir.mkdir(parents=True, exist_ok=True)
    
    # Load data
    print(f"Loading data from: {input_csv}")
    df = pd.read_csv(input_csv)
    print(f"Total rows: {len(df)}")
    
    # Determine rows to process
    if end:
        df = df.iloc[start:end]
    elif limit:
        df = df.iloc[start:start + limit]
    else:
        df = df.iloc[start:]
    
    print(f"Processing rows {start} to {start + len(df)}")
    
    style = RENDERING_STYLES.get(style_key, RENDERING_STYLES["rdkit_color"])
    
    if prompt_template is None:
        prompt_template = (
            "Please complete the chemical reaction equation by providing "
            "the main products on the right side of the arrow."
        )
    
    # Determine column names
    reaction_col = None
    for col in ['ReactionSmiles', 'mapped_reaction', 'reaction']:
        if col in df.columns:
            reaction_col = col
            break
    
    if reaction_col is None:
        raise ValueError(f"Could not find reaction column. Available: {df.columns.tolist()}")
    
    print(f"Using reaction column: {reaction_col}")
    
    qa_pairs = []
    errors = 0
    
    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Generating"):
        reaction_smiles = row[reaction_col]
        
        if pd.isna(reaction_smiles):
            errors += 1
            continue
        
        # Normalize format
        reaction_smiles = normalize_reaction_smiles(str(reaction_smiles))
        
        # Extract reactants for question
        reactants_smiles = extract_reactants(reaction_smiles)
        
        # Parse molecules
        try:
            reactant_mol = Chem.MolFromSmiles(reactants_smiles.replace(">>", ""))
            reaction_mol = rdChemReactions.ReactionFromSmarts(reaction_smiles)
        except Exception:
            errors += 1
            continue
        
        if reactant_mol is None or reaction_mol is None:
            errors += 1
            continue
        
        # Generate images
        file_idx = idx  # Use original index
        
        # Question image (reactant molecule with prompt)
        q_img = draw_molecule_style(
            reactant_mol, img_size, style, add_text=prompt_template
        )
        if q_img:
            q_img.save(questions_dir / f"{file_idx}.png")
        
        # Answer image (complete reaction)
        a_img = draw_reaction_style(reaction_smiles, img_size, style)
        if a_img:
            a_img.save(answers_dir / f"{file_idx}.png")
        
        # Metadata
        pair = {
            "id": file_idx,
            "question_image": f"questions/{file_idx}.png",
            "answer_image": f"answers/{file_idx}.png",
            "prompt": prompt_template,
            "reactants_smiles": reactants_smiles,
            "products_smiles": reaction_smiles.split(">>")[1] if ">>" in reaction_smiles else "",
            "reaction_smiles": reaction_smiles,
        }
        qa_pairs.append(pair)
    
    # Save metadata
    qa_pairs_path = output_dir / "qa_pairs.json"
    with open(qa_pairs_path, "w", encoding="utf-8") as f:
        json.dump(qa_pairs, f, ensure_ascii=False, indent=2)
    
    print(f"\nGeneration complete!")
    print(f"Successfully generated: {len(qa_pairs)}")
    print(f"Errors: {errors}")
    print(f"Output directory: {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate reaction editing dataset"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input CSV file with reaction SMILES"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./output",
        help="Output directory"
    )
    parser.add_argument(
        "--style", "-s",
        default="rdkit_color",
        choices=["rdkit_bw", "rdkit_color"],
        help="Rendering style"
    )
    parser.add_argument(
        "--img-size",
        type=int,
        default=512,
        help="Image size in pixels"
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Starting row index"
    )
    parser.add_argument(
        "--end",
        type=int,
        default=None,
        help="Ending row index (exclusive)"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=None,
        help="Limit number of rows"
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Custom prompt template"
    )
    
    args = parser.parse_args()
    generate_dataset(
        args.input,
        args.output_dir,
        args.style,
        args.img_size,
        args.start,
        args.end,
        args.limit,
        args.prompt
    )


if __name__ == "__main__":
    main()
