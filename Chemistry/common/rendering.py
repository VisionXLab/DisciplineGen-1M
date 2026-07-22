"""
Common molecular rendering utilities using RDKit and optionally Indigo.

This module provides unified rendering functions for generating molecular
structure images with various styles (black/white, color, highlight, etc.)
"""

from PIL import Image, ImageOps
import io
import random

# Try to import RDKit
try:
    from rdkit import Chem
    from rdkit.Chem.Draw import rdMolDraw2D
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False
    print("Warning: RDKit not installed.")

# Try to import Indigo (optional)
try:
    from indigo import Indigo
    from indigo.renderer import IndigoRenderer
    INDIGO_AVAILABLE = True
except ImportError:
    INDIGO_AVAILABLE = False
    print("Note: epam-indigo not installed. Using RDKit only.")


# Default rendering styles
DEFAULT_STYLES = {
    "rdkit_bw": {
        "renderer": "rdkit",
        "bg_color": (255, 255, 255),
        "use_bw_palette": True,
        "line_width_multiplier": 1.0,
    },
    "rdkit_color": {
        "renderer": "rdkit",
        "bg_color": (255, 255, 255),
        "use_bw_palette": False,
        "line_width_multiplier": 1.0,
    },
    "rdkit_bw_black_bg": {
        "renderer": "rdkit",
        "bg_color": (0, 0, 0),
        "use_bw_palette": True,
        "line_width_multiplier": 1.2,
        "invert_at_end": True,
    },
    "indigo_bw": {
        "renderer": "indigo",
        "bg_color": (255, 255, 255),
        "base_color": (0, 0, 0),
        "relative_thickness": 1.0,
    },
    "indigo_color": {
        "renderer": "indigo",
        "bg_color": (255, 255, 255),
        "coloring": True,
        "relative_thickness": 1.0,
    },
}


def draw_molecule_rdkit(
    mol,
    size: tuple = (512, 512),
    style: dict = None,
    highlight_atoms: list = None,
    highlight_colors: dict = None,
    add_annotation: bool = False
) -> Image.Image:
    """
    Render a molecule using RDKit.
    
    Args:
        mol: RDKit Mol object
        size: Image size (width, height)
        style: Style dictionary with keys:
            - bg_color: Background color tuple (R, G, B)
            - use_bw_palette: Use black/white palette
            - line_width_multiplier: Line width multiplier
            - invert_at_end: Invert colors at end (for black bg)
        highlight_atoms: List of atom indices to highlight
        highlight_colors: Dict of {atom_idx: (R, G, B)} colors
        add_annotation: Add stereo annotations
    
    Returns:
        PIL Image object
    """
    if not RDKIT_AVAILABLE or mol is None:
        return None
    
    if style is None:
        style = DEFAULT_STYLES["rdkit_color"]
    
    d2d = rdMolDraw2D.MolDraw2DCairo(size[0], size[1])
    opts = d2d.drawOptions()
    
    # Apply style settings
    bg_color = style.get("bg_color", (255, 255, 255))
    opts.bgColor = f"rgba({bg_color[0]},{bg_color[1]},{bg_color[2]},255)"
    opts.lineWidth = int(2.0 * style.get("line_width_multiplier", 1.0))
    
    if style.get("use_bw_palette"):
        opts.useBWAtomPalette()
    
    if add_annotation:
        opts.addStereoAnnotation = True
    
    # Draw molecule
    if highlight_atoms and highlight_colors:
        d2d.DrawMolecule(
            mol,
            highlightAtoms=highlight_atoms,
            highlightAtomColors=highlight_colors
        )
    else:
        d2d.DrawMolecule(mol)
    
    d2d.FinishDrawing()
    png_data = d2d.GetDrawingText()
    img = Image.open(io.BytesIO(png_data))
    
    # Handle black background inversion
    if style.get("invert_at_end"):
        img = ImageOps.invert(img.convert("RGB"))
        if img.mode == "RGB":
            img = img.convert("L").convert("RGB")
    
    if img.mode != "RGB":
        img = img.convert("RGB")
    
    return img


def draw_molecule_indigo(
    smiles: str,
    size: tuple = (512, 512),
    style: dict = None,
    highlight_atoms: list = None,
) -> Image.Image:
    """
    Render a molecule using Indigo renderer.
    
    Args:
        smiles: SMILES string of the molecule
        size: Image size (width, height)
        style: Style dictionary with keys:
            - bg_color: Background color
            - base_color: Line color
            - relative_thickness: Line thickness
            - coloring: Enable coloring
        highlight_atoms: List of atom indices to highlight
    
    Returns:
        PIL Image object
    """
    if not INDIGO_AVAILABLE:
        return None
    
    indigo = Indigo()
    renderer = IndigoRenderer(indigo)
    
    indigo_mol = indigo.loadMolecule(smiles)
    
    # Handle atom highlighting
    if highlight_atoms:
        for atom_idx in highlight_atoms:
            atom = indigo_mol.getAtom(atom_idx)
            if atom:
                atom.highlight()
        indigo.setOption("render-highlight-color", "1.0,0.0,0.0")
        indigo.setOption("render-highlight-color-enabled", True)
    
    # Apply style options
    if style:
        indigo_options = style.get("indigo_options", {})
        for key, value in indigo_options.items():
            indigo.setOption(f"render-{key}", value)
    
    indigo.setOption("render-output-format", "png")
    
    indigo_mol.layout()
    img_data = renderer.renderToBuffer(indigo_mol)
    img = Image.open(io.BytesIO(img_data))
    
    if img.mode != "RGB":
        img = img.convert("RGB")
    
    if img.size != size:
        img = img.resize(size, Image.LANCZOS)
    
    return img


def draw_molecule(
    mol_or_smiles,
    size: tuple = (512, 512),
    style_key: str = "rdkit_color",
    highlight_atoms: list = None,
    highlight_colors: dict = None,
    add_annotation: bool = False
) -> Image.Image:
    """
    Unified molecule rendering function.
    
    Args:
        mol_or_smiles: RDKit Mol object or SMILES string
        size: Image size
        style_key: One of the predefined style keys, or None for random
        highlight_atoms: List of atom indices to highlight
        highlight_colors: Dict of {atom_idx: (R, G, B)} colors
        add_annotation: Add stereo annotations
    
    Returns:
        PIL Image object
    """
    # Handle style selection
    if style_key is None:
        available_keys = ["rdkit_bw", "rdkit_color"]
        if INDIGO_AVAILABLE:
            available_keys.extend(["indigo_bw", "indigo_color"])
        style_key = random.choice(available_keys)
    
    if isinstance(style_key, str):
        style = DEFAULT_STYLES.get(style_key, DEFAULT_STYLES["rdkit_color"])
    else:
        style = style_key
    
    # Get SMILES string if mol object provided
    smiles = None
    mol = None
    
    if isinstance(mol_or_smiles, str):
        smiles = mol_or_smiles
        if RDKIT_AVAILABLE:
            mol = Chem.MolFromSmiles(smiles)
    else:
        mol = mol_or_smiles
        if mol:
            smiles = Chem.MolToSmiles(mol)
    
    # Render based on renderer type
    renderer_type = style.get("renderer", "rdkit")
    
    if renderer_type == "indigo" and INDIGO_AVAILABLE and smiles:
        return draw_molecule_indigo(
            smiles, size, style, highlight_atoms
        )
    elif RDKIT_AVAILABLE and mol:
        return draw_molecule_rdkit(
            mol, size, style, highlight_atoms, highlight_colors, add_annotation
        )
    
    return None


def get_available_styles() -> list:
    """Return list of available rendering styles."""
    styles = list(DEFAULT_STYLES.keys())
    if not INDIGO_AVAILABLE:
        styles = [s for s in styles if not s.startswith("indigo")]
    return styles


def draw_reaction_rdkit(
    reaction_smiles: str,
    size: tuple = (512, 512),
    style: dict = None,
    add_annotation: bool = False
) -> Image.Image:
    """
    Render a chemical reaction using RDKit.
    
    Args:
        reaction_smiles: Reaction SMILES string
        size: Image size
        style: Style dictionary
        add_annotation: Add annotations
    
    Returns:
        PIL Image object
    """
    if not RDKIT_AVAILABLE:
        return None
    
    try:
        rxn = Chem.rdChemReactions.ReactionFromSmarts(reaction_smiles)
        if rxn is None:
            return None
        
        if style is None:
            style = DEFAULT_STYLES["rdkit_color"]
        
        d2d = rdMolDraw2D.MolDraw2DCairo(size[0], size[1])
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
