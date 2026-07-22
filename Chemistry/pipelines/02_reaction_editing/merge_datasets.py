"""
Merge multiple reaction editing datasets.

This script merges datasets generated with different styles or row ranges
into a single unified dataset.

Usage:
    python merge_datasets.py \
        --datasets dataset1,q1/*.png,a1/*.png \
                   dataset2,q2/*.png,a2/*.png \
        --output merged

Input datasets should have:
    - questions/*.png
    - answers/*.png
    - qa_pairs.json
"""

import argparse
import json
from pathlib import Path


def merge_datasets(
    datasets: list,
    output_dir: str,
    prefix_separator: str = "_"
):
    """
    Merge multiple datasets.
    
    Args:
        datasets: List of tuples (dataset_dir, questions_pattern, answers_pattern, prefix)
        output_dir: Output directory
        prefix_separator: Separator between prefix and original filename
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    q_dir = output_path / "questions"
    a_dir = output_path / "answers"
    q_dir.mkdir(exist_ok=True)
    a_dir.mkdir(exist_ok=True)
    
    merged_pairs = []
    global_idx = 0
    
    for dataset_info in datasets:
        if len(dataset_info) == 4:
            dataset_dir, q_pattern, a_pattern, prefix = dataset_info
        else:
            dataset_dir, q_pattern, a_pattern = dataset_info
            prefix = ""
        
        dataset_path = Path(dataset_dir)
        qa_file = dataset_path / "qa_pairs.json"
        
        if not qa_file.exists():
            print(f"Warning: qa_pairs.json not found in {dataset_dir}")
            continue
        
        print(f"Processing: {dataset_dir}")
        
        with open(qa_file, 'r') as f:
            pairs = json.load(f)
        
        for pair in pairs:
            old_q_path = Path(pair['question_image'])
            old_a_path = Path(pair['answer_image'])
            
            # New filename with optional prefix
            if prefix:
                new_q_name = f"{prefix}{prefix_separator}{old_q_path.name}"
                new_a_name = f"{prefix}{prefix_separator}{old_a_path.name}"
            else:
                new_q_name = old_q_path.name
                new_a_name = old_a_path.name
            
            # Copy images
            import shutil
            src_q = dataset_path / old_q_path
            src_a = dataset_path / old_a_path
            
            if src_q.exists():
                shutil.copy(src_q, q_dir / new_q_name)
            if src_a.exists():
                shutil.copy(src_a, a_dir / new_a_name)
            
            # Update metadata
            merged_pairs.append({
                "id": global_idx,
                "question_image": f"questions/{new_q_name}",
                "answer_image": f"answers/{new_a_name}",
                "prompt": pair.get("prompt", ""),
                "reactants_smiles": pair.get("reactants_smiles", ""),
                "products_smiles": pair.get("products_smiles", ""),
                "reaction_smiles": pair.get("reaction_smiles", ""),
                "source": str(dataset_dir),
                "original_id": pair.get("id", -1),
            })
            
            global_idx += 1
        
        print(f"  Added {len(pairs)} pairs")
    
    # Save merged metadata
    output_qa_file = output_path / "qa_pairs.json"
    with open(output_qa_file, 'w', encoding='utf-8') as f:
        json.dump(merged_pairs, f, ensure_ascii=False, indent=2)
    
    print(f"\nMerge complete!")
    print(f"Total pairs: {len(merged_pairs)}")
    print(f"Output: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Merge multiple reaction editing datasets"
    )
    parser.add_argument(
        "--datasets", "-d",
        nargs='+',
        required=True,
        help="Datasets to merge (format: dir:q_pattern:a_pattern[:prefix])"
    )
    parser.add_argument(
        "--output", "-o",
        default="./merged",
        help="Output directory"
    )
    parser.add_argument(
        "--separator", "-s",
        default="_",
        help="Prefix separator"
    )
    
    args = parser.parse_args()
    
    # Parse datasets
    datasets = []
    for d in args.datasets:
        parts = d.split(':')
        datasets.append(parts)
    
    merge_datasets(datasets, args.output, args.separator)


if __name__ == "__main__":
    main()
