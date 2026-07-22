"""
Renumber dataset images sequentially.

This script renumbers images in a dataset from 0 to N sequentially,
updating all metadata references.

Usage:
    python renumber_dataset.py --input ./dataset --output ./renumbered
"""

import argparse
import json
import shutil
from pathlib import Path


def renumber_dataset(input_dir: str, output_dir: str):
    """
    Renumber dataset images sequentially.
    
    Args:
        input_dir: Input dataset directory
        output_dir: Output dataset directory
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    # Create output directories
    q_out = output_path / "questions"
    a_out = output_path / "answers"
    q_out.mkdir(parents=True, exist_ok=True)
    a_out.mkdir(parents=True, exist_ok=True)
    
    # Load and sort existing pairs
    qa_file = input_path / "qa_pairs.json"
    if qa_file.exists():
        with open(qa_file, 'r') as f:
            pairs = json.load(f)
        
        # Sort by original ID
        pairs.sort(key=lambda x: x.get('id', 0))
    else:
        print(f"Warning: {qa_file} not found. Renumbering by file order.")
        pairs = []
    
    # Process files
    renamed = []
    new_id = 0
    
    for pair in pairs:
        old_q_path = Path(pair['question_image'])
        old_a_path = Path(pair['answer_image'])
        
        old_q = input_path / old_q_path
        old_a = input_path / old_a_path
        
        if old_q.exists() and old_a.exists():
            # Copy with new names
            new_q_name = f"{new_id}.png"
            new_a_name = f"{new_id}.png"
            
            shutil.copy(old_q, q_out / new_q_name)
            shutil.copy(old_a, a_out / new_a_name)
            
            # Update metadata
            renamed.append({
                "id": new_id,
                "question_image": f"questions/{new_q_name}",
                "answer_image": f"answers/{new_a_name}",
                "prompt": pair.get("prompt", ""),
                "reactants_smiles": pair.get("reactants_smiles", ""),
                "products_smiles": pair.get("products_smiles", ""),
                "reaction_smiles": pair.get("reaction_smiles", ""),
            })
            
            new_id += 1
    
    # Save updated metadata
    output_qa_file = output_path / "qa_pairs.json"
    with open(output_qa_file, 'w', encoding='utf-8') as f:
        json.dump(renamed, f, ensure_ascii=False, indent=2)
    
    print(f"Renumbered {len(renamed)} image pairs")
    print(f"Output: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Renumber dataset images sequentially"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input dataset directory"
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="Output dataset directory"
    )
    
    args = parser.parse_args()
    renumber_dataset(args.input, args.output)


if __name__ == "__main__":
    main()
