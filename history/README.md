# Historical Basemaps Map Renderer

A script for batch rendering historical map visualizations with random styling and label masking.

## Prerequisites

First, clone the historical basemaps repository:

```bash
git clone https://github.com/aourednik/historical-basemaps.git
```

## Dependencies

Install the required packages:

```bash
pip install geopandas matplotlib numpy shapely
```

## Usage

Edit the configuration section in `plotv2.py` to set your paths and parameters:

```python
INPUT_DIR    = "path/to/historical-basemaps/geojson"
OUTPUT_DIR   = "geojson_output_v2"
LABEL_COL    = "NAME"
NUM_CROPS    = 50      # Number of random render pairs per geojson
NUM_MASK     = 2       # Number of labels to mask per pair
MIN_VISIBLE  = 5       # Minimum visible labels
MAX_VISIBLE  = 8       # Maximum visible labels
MAX_TRIES    = 100     # Max attempts to find suitable scale
DPI          = 300     # Output resolution
```

Then run:

```bash
python plotv2.py
```

## Output

The script generates pairs of images in `output_dir/input/` and `output_dir/gt/`:
- `*_gt.png`: Ground truth images with all labels visible
- `*_input.png`: Input images with some labels masked

Metadata is saved to `output_dir/meta.json`.

## Data Source

Historical boundary data from [historical-basemaps](https://github.com/aourednik/historical-basemaps).

