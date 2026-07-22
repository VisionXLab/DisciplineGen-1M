"""
Filter molecules by row range.

This script filters molecules from an Excel/CSV file by selecting a specific
row range. Useful for processing large datasets in parallel.

Usage:
    python filter_compounds.py --input compounds.xlsx --output output.xlsx \
        --start 70000 --limit 40000

Input data format (Excel/CSV):
    Must contain SMILES column ('Smiles' or 'Smile') and optionally 'Records Name'
"""

import argparse
import pandas as pd


def filter_by_row_range(
    input_file: str,
    output_file: str,
    start: int = 0,
    limit: int = None
):
    """
    Filter molecules by row range.
    
    Args:
        input_file: Path to input Excel/CSV file
        output_file: Path to output Excel/CSV file
        start: Starting row index (0-based)
        limit: Maximum number of rows to output
    """
    print(f"Loading data from: {input_file}")
    
    if input_file.endswith('.xlsx'):
        df = pd.read_excel(input_file)
    else:
        df = pd.read_csv(input_file)
    
    total_rows = len(df)
    print(f"Total rows in file: {total_rows}")
    
    # Apply row range
    df_filtered = df.iloc[start:]
    
    if limit:
        df_filtered = df_filtered.head(limit)
    
    print(f"Selected rows: {start} to {start + len(df_filtered)}")
    print(f"Output rows: {len(df_filtered)}")
    
    # Save result
    print(f"Saving to: {output_file}")
    if output_file.endswith('.xlsx'):
        df_filtered.to_excel(output_file, index=False)
    else:
        df_filtered.to_csv(output_file, index=False)
    
    print("Done!")


def main():
    parser = argparse.ArgumentParser(
        description="Filter molecules by row range"
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
        "--start", "-s",
        type=int,
        default=0,
        help="Starting row index (0-based, default: 0)"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=None,
        help="Maximum number of rows to output"
    )
    
    args = parser.parse_args()
    filter_by_row_range(
        args.input,
        args.output,
        args.start,
        args.limit
    )


if __name__ == "__main__":
    main()
