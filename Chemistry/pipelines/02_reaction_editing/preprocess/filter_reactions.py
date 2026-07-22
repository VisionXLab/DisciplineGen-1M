"""
Filter reactions by confidence and product conditions.

This script filters reaction data from USPTO dataset:
1. Only keep reactions where confident == TRUE
2. Only keep reactions where product (right of '>>') contains no '.' (single product)

Usage:
    python filter_reactions.py --input reactions.csv --output filtered_reactions.csv

Input CSV columns expected:
    - mapped_reaction: Full reaction SMILES
    - confident: Confidence flag (TRUE/FALSE)
"""

import argparse
import pandas as pd


def filter_reactions(input_file, output_file):
    """
    Filter reactions by confidence and product conditions.
    
    Args:
        input_file: Path to input CSV file
        output_file: Path to output CSV file
    """
    print(f"Loading data from: {input_file}")
    df = pd.read_csv(input_file)
    print(f"Total rows: {len(df)}")
    
    # Check for required columns
    if 'mapped_reaction' not in df.columns:
        # Try alternative column name
        for col in ['ReactionSmiles', 'reaction', 'rxn']:
            if col in df.columns:
                reaction_col = col
                break
        else:
            raise ValueError(f"Could not find reaction column. Available: {df.columns.tolist()}")
    else:
        reaction_col = 'mapped_reaction'
    
    print(f"Using reaction column: {reaction_col}")
    
    # Filter by confidence
    mask_confident = (
        (df['confident'] == True) | 
        (df['confident'].astype(str).str.upper() == 'TRUE')
    )
    
    # Filter by single product (no '.' in product)
    def check_singleton(product_str):
        if pd.isna(product_str):
            return False
        return '.' not in product_str.strip()
    
    def get_product(reaction):
        if pd.isna(reaction) or '>>' not in reaction:
            return ""
        return reaction.split('>>')[1]
    
    df['_product'] = df[reaction_col].apply(get_product)
    mask_singleton = df['_product'].apply(check_singleton)
    df = df.drop(columns=['_product'])
    
    # Apply filters
    filtered_df = df[mask_confident & mask_singleton]
    
    print(f"\nFiltering results:")
    print(f"  Confident reactions: {mask_confident.sum()}")
    print(f"  Single product reactions: {mask_singleton.sum()}")
    print(f"  After both filters: {len(filtered_df)}")
    print(f"\nSaving to: {output_file}")
    
    filtered_df.to_csv(output_file, index=False)
    print("Done!")


def main():
    parser = argparse.ArgumentParser(
        description="Filter reactions by confidence and product conditions"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input CSV file path"
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="Output CSV file path"
    )
    
    args = parser.parse_args()
    filter_reactions(args.input, args.output)


if __name__ == "__main__":
    main()
