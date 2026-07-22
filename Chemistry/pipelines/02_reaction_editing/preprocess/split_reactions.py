"""
Split reaction SMILES into reactants and products.

This script parses reaction SMILES strings and extracts:
- reactants: Everything before '>>'
- products: Everything after '>>'

Supports both formats:
- "reactants>>products"
- "reactants>conditions>products"

Usage:
    python split_reactions.py --csv reactions.csv --output split_reactions.csv
    
    python split_reactions.py --csv reactions.csv \
        --reaction-column ReactionSmiles \
        --reactants-column reactants \
        --products-column products
"""

import argparse
import logging
from pathlib import Path
import pandas as pd


def split_reaction_smiles(reaction_smiles: str) -> tuple:
    """
    Split a reaction SMILES string into reactants and products.
    
    Args:
        reaction_smiles: Reaction SMILES string
    
    Returns:
        Tuple of (reactants_with_arrow, products)
        - For "reactants>>products": returns ("reactants>>", "products")
        - For "reactants>conditions>products": returns ("reactants>conditions>", "products")
    """
    if pd.isna(reaction_smiles) or not isinstance(reaction_smiles, str):
        return "", ""
    
    count = reaction_smiles.count('>')
    
    if count == 0:
        logging.warning(f"Reaction SMILES without '>': {reaction_smiles[:50]}...")
        return reaction_smiles.strip(), ""
    
    if ">>" in reaction_smiles:
        parts = reaction_smiles.rsplit(">>", 1)
        reactants = parts[0].strip() + ">>"
        products = parts[1].strip() if len(parts) > 1 else ""
    else:
        parts = reaction_smiles.rsplit(">", 1)
        reactants = parts[0].strip() + ">"
        products = parts[1].strip() if len(parts) > 1 else ""
    
    return reactants, products


def split_reactions(
    input_csv: str,
    output_csv: str,
    reaction_column: str = "ReactionSmiles",
    reactants_column: str = "reactants",
    products_column: str = "products",
    limit: int = None
):
    """
    Split reactions in CSV file.
    
    Args:
        input_csv: Input CSV file path
        output_csv: Output CSV file path
        reaction_column: Name of column containing reaction SMILES
        reactants_column: Name for new reactants column
        products_column: Name for new products column
        limit: Optional limit on number of rows to process
    """
    csv_path = Path(input_csv).expanduser().resolve()
    
    print(f"Loading CSV file: {csv_path}")
    df = pd.read_csv(csv_path)
    
    if limit:
        df = df.head(limit)
        print(f"Limited to first {limit} rows")
    
    print(f"Total rows: {len(df)}")
    
    if reaction_column not in df.columns:
        raise ValueError(
            f"Column '{reaction_column}' not found. Available: {df.columns.tolist()}"
        )
    
    print(f"Splitting reactions from column: {reaction_column}")
    
    # Split reactions
    split_results = df[reaction_column].apply(split_reaction_smiles)
    reactants_list = [r[0] for r in split_results]
    products_list = [r[1] for r in split_results]
    
    # Add new columns
    df[reactants_column] = reactants_list
    df[products_column] = products_list
    
    # Statistics
    reactions_with_products = sum(1 for p in products_list if p)
    print(f"Reactions with products: {reactions_with_products}")
    
    print(f"\nSaving to: {output_csv}")
    df.to_csv(output_csv, index=False)
    print("Done!")


def main():
    parser = argparse.ArgumentParser(
        description="Split reaction SMILES into reactants and products"
    )
    parser.add_argument(
        "--csv", "-c",
        required=True,
        help="Input CSV file path"
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="Output CSV file path"
    )
    parser.add_argument(
        "--reaction-column",
        default="ReactionSmiles",
        help="Column name containing reaction SMILES"
    )
    parser.add_argument(
        "--reactants-column",
        default="reactants",
        help="Name for reactants column"
    )
    parser.add_argument(
        "--products-column",
        default="products",
        help="Name for products column"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=None,
        help="Limit number of rows to process"
    )
    
    args = parser.parse_args()
    split_reactions(
        args.csv,
        args.output,
        args.reaction_column,
        args.reactants_column,
        args.products_column,
        args.limit
    )


if __name__ == "__main__":
    main()
