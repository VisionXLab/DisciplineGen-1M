# Release Checklist

Use this checklist before publishing the dataset-construction code.

## Scope

- Keep source code, README files, examples, and small assets required by the renderers.
- Exclude raw archives, downloaded datasets, generated images, annotation shards, engine binaries, model files, and local scratch outputs.
- Exclude all private keys, tokens, passwords, cluster credentials, and machine-specific config files.

## Security

- Run `python scripts/check_release_safety.py .` before packaging or pushing.
- Confirm that `.env` files are not committed. Use `.env.example` for documentation.
- Confirm that private key paths such as `ailab_ssh_key/` are ignored and not included in release archives.
- Do not commit API keys. Current public-source downloaders use public HTTP endpoints and do not require API keys.

## Reproducibility

- Document external data sources in README files instead of committing large raw data.
- Document engine paths through CLI arguments or environment variables.
- Keep generated outputs under `outputs/` or another ignored directory.
- Prefer commands with explicit `--input`, `--output-root`, `--max-samples`, `--image-size`, and `--seed`.

## Suggested Open-Source Package Contents

- `scripts/`
- `requirements.txt`
- `.env.example`
- `.gitignore`
- `RELEASE_CHECKLIST.md`

Do not include `raw_data/`, `outputs/`, `tmp*/`, `ailab_ssh_key/`, downloaded archives, or engine/model binaries.

