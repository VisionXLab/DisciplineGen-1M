"""
Generate molecule editing dataset.

This script generates QA image pairs for molecule editing task:
- Question: Original molecule with highlighted positions
- Answer: Modified molecule with inserted fragments

Editing rules:
- Randomly select 1-3 sp2 hybridized carbon atoms
- Insert chemical fragments (ethyl, phenyl, cyclopropyl, etc.) at selected positions
- Constraint: Adjacent atoms and atoms in the same ring are not selected simultaneously

Usage:
    python generate_dataset.py --input filtered_compounds.xlsx --output-dir ./output

Output structure:
    output/
    ├── questions/*.png      # Original molecule + highlight
    ├── answers/*.png        # Modified molecule
    └── metadata.jsonl       # Metadata with instructions and SMILES
"""

import os
import sys
import json
import random
import argparse
from pathlib import Path

import pandas as pd
from rdkit import Chem
from rdkit.Chem import rdMolDraw2D
from PIL import Image, ImageOps
import io
from tqdm import tqdm

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "common"))
from utils import smiles_to_mol
from rendering import draw_molecule


# Fragment library with SMILES
FRAGMENTS = {
    "ethyl": "CC-[*:1]",
    "isopropyl": "CC(C)-[*:1]",
    "cyclopropyl": "C1CC1-[*:1]",
    "cyclobutyl": "C1CCC1-[*:1]",
    "cyclopentyl": "C1CCCC1-[*:1]",
    "cyclohexyl": "C1CCCCC1-[*:1]",
    "phenyl": "c1ccccc1-[*:1]",
    "p_tolyl": "Cc1ccccc1-[*:1]",
    "methoxy": "COC-[*:1]",
    "ethoxy": "CCOC-[*:1]",
    "methylamino": "CNC-[*:1]",
    "dimethylamino": "CN(C)C-[*:1]",
}

MAX_INSERTIONS = 3

# Prompt templates
PROMPT_TEMPLATES = [
    lambda f, c: f"Add {f} at the {c} highlighted position.",
    lambda f, c: f"Please attach {f} to the {c} highlighted site.",
    lambda f, c: f"Introduce {f} at the {c} marked atom.",
    lambda f, c: f"Insert {f} into the {c} highlighted position.",
    lambda f, c: f"Connect {f} with the {c} highlighted carbon.",
    lambda f, c: f"Attach {f} to the {c} position indicated in the molecule.",
    lambda f, c: f"Add the {f} group at the {c} atom marked on the structure.",
    lambda f, c: f"Place {f} at the {c} highlighted attachment point.",
    lambda f, c: f"Functionalize the {c} highlighted position with {f}.",
    lambda f, c: f"Modify the {c} highlighted site by adding {f}.",
]

COLOR_MODE_APPENDIX = (
    " The drawing should be precise, following standard chemical drawing conventions. "
    "Use standard conventions for element coloring (e.g., blue for nitrogen, red for oxygen, "
    "yellow for sulfur, orange for phosphorus). Clear the highlight annotation at the insertion position."
)


def get_sp2_carbon_candidates(mol, used_indices=None, forbidden_neighbors=None):
    """
    Find sp2 hybridized carbon atoms suitable for fragment insertion.
    
    Args:
        mol: RDKit Mol object
        used_indices: Set of already used atom indices
        forbidden_neighbors: Set of forbidden atom indices (neighbors of used atoms)
    
    Returns:
        List of atom indices that are eligible for modification
    """
    if used_indices is None:
        used_indices = set()
    if forbidden_neighbors is None:
        forbidden_neighbors = set()
    
    # Calculate forbidden set (neighbors of forbidden atoms)
    forbidden_set = set()
    for idx in forbidden_neighbors:
        atom = mol.GetAtomWithIdx(idx)
        for neighbor in atom.GetNeighbors():
            forbidden_set.add(neighbor.GetIdx())
    
    candidates = []
    for atom in mol.GetAtoms():
        if (atom.GetSymbol() == 'C'
            and atom.GetHybridization() == Chem.HybridizationType.SP2
            and atom.GetIdx() not in used_indices
            and atom.GetIdx() not in forbidden_set
            and atom.GetTotalNumHs() >= 1):
            candidates.append(atom.GetIdx())
    
    return candidates


def get_atoms_in_same_ring(mol, atom_idx):
    """Get all atom indices in the same ring as atom_idx."""
    ring_atoms = set()
    ring_info = mol.GetRingInfo()
    for ring in ring_info.AtomRings():
        if atom_idx in ring:
            ring_atoms.update(ring)
    ring_atoms.discard(atom_idx)
    return ring_atoms


def insert_fragment_to_mol(current_mol, target_idx, frag_smiles):
    """
    Insert a fragment at the target atom position.
    
    Args:
        current_mol: Current molecule
        target_idx: Index of atom to attach fragment
        frag_smiles: Fragment SMILES with [*:1] attachment point
    
    Returns:
        Modified molecule or None if insertion fails
    """
    frag = Chem.MolFromSmiles(frag_smiles)
    if not frag:
        return None
    
    # Combine molecules
    combined = Chem.CombineMols(current_mol, frag)
    ed_mol = Chem.EditableMol(combined)
    
    # Find dummy atom [*:1] index
    offset = current_mol.GetNumAtoms()
    dummy_idx = -1
    for atom in frag.GetAtoms():
        if atom.GetSymbol() == '*':
            dummy_idx = atom.GetIdx() + offset
            break
    
    if dummy_idx == -1:
        return None
    
    # Find atom connected to dummy
    neighbors = combined.GetAtomWithIdx(dummy_idx).GetNeighbors()
    if not neighbors:
        return None
    frag_attach_idx = neighbors[0].GetIdx()
    
    # Create bond
    ed_mol.AddBond(target_idx, frag_attach_idx, order=Chem.rdchem.BondType.SINGLE)
    
    # Remove dummy atom
    ed_mol.RemoveAtom(dummy_idx)
    
    # Sanitize and return
    new_mol = ed_mol.GetMol()
    try:
        Chem.SanitizeMol(new_mol)
        return new_mol
    except Exception:
        return None


def edit_molecule_multifragment(base_smiles, num_fragments):
    """
    Perform multiple fragment insertions on a molecule.
    
    Args:
        base_smiles: Original molecule SMILES
        num_fragments: Number of fragments to insert (1-3)
    
    Returns:
        Tuple of (modified_mol, modified_indices, fragment_names, final_smiles)
        or (None, [], [], None) if failed
    """
    mol = smiles_to_mol(base_smiles)
    if not mol:
        return None, [], [], None
    
    current_mol = mol
    modified_indices = []
    inserted_fragments = []
    used_atom_indices = set()
    forbidden_indices = set()
    
    for _ in range(num_fragments):
        # Find candidates
        possible_atoms = get_sp2_carbon_candidates(
            current_mol, used_atom_indices, forbidden_indices
        )
        
        if not possible_atoms:
            break
        
        # Random selection
        target_idx = random.choice(possible_atoms)
        frag_name = random.choice(list(FRAGMENTS.keys()))
        frag_smiles = FRAGMENTS[frag_name]
        
        # Insert fragment
        new_mol = insert_fragment_to_mol(current_mol, target_idx, frag_smiles)
        
        if new_mol:
            current_mol = new_mol
            modified_indices.append(target_idx)
            inserted_fragments.append(frag_name)
            used_atom_indices.add(target_idx)
            
            # Update forbidden indices
            for neighbor in current_mol.GetAtomWithIdx(target_idx).GetNeighbors():
                forbidden_indices.add(neighbor.GetIdx())
            forbidden_indices.update(get_atoms_in_same_ring(current_mol, target_idx))
        else:
            break
    
    if modified_indices:
        final_smiles = Chem.MolToSmiles(current_mol)
        return current_mol, modified_indices, inserted_fragments, final_smiles
    
    return None, [], [], None


def draw_molecule_with_highlight(mol, highlight_indices, size=512):
    """
    Draw molecule with highlighted atoms.
    
    Args:
        mol: RDKit Mol object
        highlight_indices: List of atom indices to highlight
        size: Image size
    
    Returns:
        PIL Image
    """
    d2d = rdMolDraw2D.MolDraw2DCairo(size, size)
    opts = d2d.drawOptions()
    opts.bgColor = "rgba(255,255,255,255)"
    
    colors = [
        (1.0, 0.0, 0.0),  # Red
        (0.0, 1.0, 0.0),  # Green
        (0.0, 0.0, 1.0),   # Blue
    ]
    highlight_colors = {
        idx: colors[i % len(colors)] 
        for i, idx in enumerate(highlight_indices)
    }
    
    d2d.DrawMolecule(
        mol,
        highlightAtoms=list(highlight_indices),
        highlightAtomColors=highlight_colors
    )
    d2d.FinishDrawing()
    
    png_data = d2d.GetDrawingText()
    img = Image.open(io.BytesIO(png_data))
    if img.mode != "RGB":
        img = img.convert("RGB")
    
    return img


def build_instruction(frag_names, color_names):
    """Build natural language instruction from fragments and colors."""
    # Format fragment list
    if len(frag_names) == 1:
        frag_list = f"a {frag_names[0]} group"
    else:
        frag_parts = [f"a {frag} group" for frag in frag_names]
        frag_list = " and ".join([", ".join(frag_parts[:-1]), frag_parts[-1]])
    
    # Format color list
    if len(color_names) == 1:
        color_list = f"the {color_names[0]} highlighted position"
    else:
        color_parts = [f"the {color} highlighted position" for color in color_names]
        color_list = " and ".join([", ".join(color_parts[:-1]), color_parts[-1]])
    
    # Random template
    template_func = random.choice(PROMPT_TEMPLATES)
    instruction = template_func(frag_list, color_list)
    
    # Add color mode appendix
    instruction += COLOR_MODE_APPENDIX
    
    return instruction


def generate_dataset(input_file, output_dir, img_size=512, limit=None):
    """
    Generate molecule editing dataset.
    
    Args:
        input_file: Path to input Excel/CSV file with SMILES column
        output_dir: Output directory
        img_size: Image size in pixels
        limit: Maximum number of molecules to process
    """
    # Setup directories
    output_dir = Path(output_dir)
    questions_dir = output_dir / "questions"
    answers_dir = output_dir / "answers"
    
    questions_dir.mkdir(parents=True, exist_ok=True)
    answers_dir.mkdir(parents=True, exist_ok=True)
    
    # Load data
    print(f"Loading data from: {input_file}")
    df = pd.read_excel(input_file) if input_file.endswith('.xlsx') else pd.read_csv(input_file)
    
    # Find SMILES column
    smile_col = None
    for col in ['Smiles', 'Smile', 'smiles', 'smile']:
        if col in df.columns:
            smile_col = col
            break
    
    if smile_col is None:
        raise ValueError("Could not find SMILES column")
    
    smiles_list = df[smile_col].dropna().tolist()
    if limit:
        smiles_list = smiles_list[:limit]
    
    print(f"Processing {len(smiles_list)} molecules...")
    
    metadata = []
    color_names = ['Red', 'Green', 'Blue']
    
    for i, base_smiles in enumerate(tqdm(smiles_list)):
        # Random number of insertions (1-3)
        num_insertions = random.randint(1, MAX_INSERTIONS)
        
        # Perform editing
        new_mol, modified_indices, frag_names, new_smiles = edit_molecule_multifragment(
            base_smiles, num_insertions
        )
        
        if new_mol and modified_indices:
            orig_mol = smiles_to_mol(base_smiles)
            if not orig_mol:
                continue
            
            # Draw question (original with highlight)
            q_img = draw_molecule_with_highlight(
                orig_mol, modified_indices, img_size
            )
            q_path = f"questions/{i}.png"
            q_img.save(questions_dir / f"{i}.png")
            
            # Draw answer (modified molecule)
            a_img = draw_molecule(new_mol, size=(img_size, img_size))
            a_path = f"answers/{i}.png"
            a_img.save(answers_dir / f"{i}.png")
            
            # Build instruction
            selected_colors = [color_names[j % len(color_names)] for j in range(len(frag_names))]
            instruction = build_instruction(frag_names, selected_colors)
            
            # Metadata entry
            entry = {
                "id": i,
                "original_smiles": base_smiles,
                "modified_smiles": new_smiles,
                "inserted_fragments": frag_names,
                "instruction": instruction,
                "question_image": q_path,
                "answer_image": a_path,
            }
            metadata.append(entry)
    
    # Save metadata
    metadata_path = output_dir / "metadata.jsonl"
    with open(metadata_path, "w", encoding="utf-8") as f:
        for entry in metadata:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    print(f"\nDone! Generated {len(metadata)} pairs")
    print(f"Output directory: {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate molecule editing dataset"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input Excel/CSV file with SMILES data"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./output",
        help="Output directory (default: ./output)"
    )
    parser.add_argument(
        "--img-size",
        type=int,
        default=512,
        help="Image size in pixels (default: 512)"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=None,
        help="Limit number of molecules to process"
    )
    
    args = parser.parse_args()
    generate_dataset(args.input, args.output_dir, args.img_size, args.limit)


if __name__ == "__main__":
    main()
