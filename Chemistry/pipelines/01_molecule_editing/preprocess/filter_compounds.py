"""
Filter molecules by atom count.

This script filters compounds from a source Excel file based on atom count:
- Molecules with < 20 atoms: keep all
- Molecules with 20-30 atoms: sample 50%
- Molecules with > 30 atoms: discard

Usage:
    python filter_compounds.py --input input.xlsx --output output.xlsx

Input data format (Excel/CSV):
    Must contain a column with SMILES data (column name: 'Smiles' or 'Smile')
"""

import argparse
import pandas as pd
from rdkit import Chem


def count_atoms(smiles: str) -> int:
    """Count number of atoms in a SMILES molecule."""
    if pd.isna(smiles) or not isinstance(smiles, str):
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        return mol.GetNumAtoms() if mol else None
    except Exception:
        return None


def filter_molecules(
    input_file: str,
    output_file: str,
    max_atoms: int = 30,
    sample_fraction: float = 0.5,
    random_state: int = 42
):
    """
    Filter molecules by atom count.
    
    Args:
        input_file: Path to input Excel/CSV file
        output_file: Path to output Excel file
        max_atoms: Maximum atom count threshold
        sample_fraction: Fraction to sample for molecules in range [20, max_atoms]
        random_state: Random seed for reproducibility
    """
    print(f"Loading data from: {input_file}")
    df = pd.read_excel(input_file) if input_file.endswith('.xlsx') else pd.read_csv(input_file)
    print(f"Total rows: {len(df)}")
    
    # Find SMILES column
    smile_col = None
    for col in ['Smiles', 'Smile', 'smiles', 'smile']:
        if col in df.columns:
            smile_col = col
            break
    
    if smile_col is None:
        print(f"Available columns: {df.columns.tolist()}")
        raise ValueError("Could not find SMILES column")
    
    print(f"Using SMILES column: {smile_col}")
    
    # Calculate atom counts
    print("Calculating atom counts...")
    df['_atom_count'] = df[smile_col].apply(count_atoms)
    
    # Filter valid molecules
    valid_df = df[df['_atom_count'].notna()].copy()
    print(f"Valid molecules: {len(valid_df)}")
    
    # Apply filtering rules
    lt_20 = valid_df[valid_df['_atom_count'] < 20]
    between_20_30 = valid_df[
        (valid_df['_atom_count'] >= 20) & 
        (valid_df['_atom_count'] <= max_atoms)
    ]
    
    print(f"Molecules with < 20 atoms: {len(lt_20)}")
    print(f"Molecules with 20-{max_atoms} atoms: {len(between_20_30)}")
    
    # Sample from between group
    sampled = between_20_30.sample(
        frac=sample_fraction, 
        random_state=random_state
    )
    print(f"Sampled from 20-{max_atoms} group: {len(sampled)}")
    
    # Combine
    result = pd.concat([lt_20, sampled], ignore_index=True)
    result = result.drop(columns=['_atom_count'])
    
    print(f"\nTotal after filtering: {len(result)}")
    print(f"Saving to: {output_file}")
    
    # Save result
    if output_file.endswith('.xlsx'):
        result.to_excel(output_file, index=False)
    else:
        result.to_csv(output_file, index=False)
    
    print("Done!")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Filter molecules by atom count"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input Excel/CSV file path"
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="Output Excel/CSV file path"
    )
    parser.add_argument(
        "--max-atoms",
        type=int,
        default=30,
        help="Maximum atom count (default: 30)"
    )
    parser.add_argument(
        "--sample-fraction",
        type=float,
        default=0.5,
        help="Fraction to sample from 20-max_atoms group (default: 0.5)"
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random state for reproducibility (default: 42)"
    )
    
    args = parser.parse_args()
    filter_molecules(
        args.input,
        args.output,
        args.max_atoms,
        args.sample_fraction,
        args.random_state
    )


if __name__ == "__main__":
    main()
