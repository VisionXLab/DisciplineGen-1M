"""
Common utility functions for chemical data processing.
"""

from rdkit import Chem
from rdkit.Chem import rdChemReactions


def normalize_reaction_smiles(smiles: str) -> str:
    """
    Normalize reaction SMILES format.
    
    Converts reactions with single '>' separators to '>>' format.
    
    Args:
        smiles: Reaction SMILES string (e.g., "reactants>conditions>products")
    
    Returns:
        Normalized SMILES with '>>' separator
    
    Examples:
        >>> normalize_reaction_smiles("CCO.CC>>CCOC")
        'CCO.CC>>CCOC'
        >>> normalize_reaction_smiles("CC>O>>CCO")
        'CC>>CCO'
    """
    if not smiles or not isinstance(smiles, str):
        return smiles
    
    if ">>" in smiles:
        return smiles
    
    if ">" in smiles:
        parts = smiles.split(">")
        reactants_conditions = ".".join(parts[:-1])
        products = parts[-1]
        return f"{reactants_conditions}>>{products}"
    
    return smiles


def split_reaction_smiles(reaction_smiles: str) -> tuple:
    """
    Split reaction SMILES into reactants and products.
    
    Args:
        reaction_smiles: Reaction SMILES string
    
    Returns:
        Tuple of (reactants, products), both include the separator '>>'
    """
    if not reaction_smiles or not isinstance(reaction_smiles, str):
        return "", ""
    
    if ">>" not in reaction_smiles:
        return reaction_smiles, ""
    
    parts = reaction_smiles.rsplit(">>", 1)
    reactants = parts[0].strip() + ">>"
    products = parts[1].strip() if len(parts) > 1 else ""
    
    return reactants, products


def clear_atom_mapping(mol):
    """
    Remove atom mapping numbers from molecule.
    
    Args:
        mol: RDKit Mol object
    
    Returns:
        Mol object with all atom map numbers set to 0
    """
    if mol is None:
        return None
    
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)
    
    return mol


def clear_reaction_atom_mapping(reaction_smiles: str) -> str:
    """
    Remove atom mapping numbers from reaction SMILES.
    
    Args:
        reaction_smiles: Reaction SMILES string with atom mappings
    
    Returns:
        Reaction SMILES without atom mapping numbers
    """
    if not reaction_smiles:
        return reaction_smiles
    
    # Remove :number patterns
    import re
    return re.sub(r':\d+]', ']', reaction_smiles)


def smiles_to_mol(smiles: str, sanitize: bool = True):
    """
    Convert SMILES string to RDKit Mol object with error handling.
    
    Args:
        smiles: SMILES string
        sanitize: Whether to sanitize the molecule
    
    Returns:
        RDKit Mol object or None if parsing fails
    """
    if not smiles or not isinstance(smiles, str):
        return None
    
    try:
        mol = Chem.MolFromSmiles(smiles, sanitize=sanitize)
        return mol
    except Exception:
        return None


def count_atoms(smiles: str) -> int:
    """
    Count number of atoms in a molecule.
    
    Args:
        smiles: SMILES string
    
    Returns:
        Number of atoms, or None if parsing fails
    """
    mol = smiles_to_mol(smiles)
    return mol.GetNumAtoms() if mol else None


def get_reaction_from_smiles(reaction_smiles: str):
    """
    Parse reaction SMILES to RDKit Reaction object.
    
    Args:
        reaction_smiles: Reaction SMILES string
    
    Returns:
        RDKit Reaction object or None if parsing fails
    """
    if not reaction_smiles:
        return None
    
    try:
        reaction = rdChemReactions.ReactionFromSmarts(reaction_smiles)
        return reaction
    except Exception:
        return None


def validate_reaction(reaction_smiles: str) -> bool:
    """
    Validate if a reaction SMILES string is well-formed.
    
    Args:
        reaction_smiles: Reaction SMILES string
    
    Returns:
        True if valid, False otherwise
    """
    if not reaction_smiles or not isinstance(reaction_smiles, str):
        return False
    
    try:
        reaction = rdChemReactions.ReactionFromSmarts(reaction_smiles)
        return reaction is not None
    except Exception:
        return False


def filter_singletons_from_product(product_smiles: str) -> bool:
    """
    Check if product has only one molecule (no '.' separator).
    
    Args:
        product_smiles: Product SMILES string (after '>>')
    
    Returns:
        True if single product, False if multiple products
    """
    if not product_smiles:
        return False
    
    return '.' not in product_smiles.strip()
