# 2D Math Task Renderers

Scripts for generating input/GT image pairs for 2D geometry tasks.

## Dependencies

```bash
pip install matplotlib numpy tqdm
```

## Scripts

- `line_point_task_render.py` - Generates point and line geometry tasks
- `reflection_task_render.py` - Generates symmetry/reflection tasks
- `rotation_task_render.py` - Generates rotation-around-point tasks
- `scaling_task_render.py` - Generates area scaling tasks
- `translation_task_render.py` - Generates translation tasks
- `triangle_task_render.py` - Generates triangle geometry tasks

## Usage

Run any script:

```bash
python <script_name>.py
```

Output directories: `input/`, `gt/`, `meta/` with `meta.json`.