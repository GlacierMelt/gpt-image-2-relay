---
name: gpt-image-2-relay
description: Generate or edit raster images with GPT Image 2 through the user's OpenAI-compatible relay. Use when the user asks to use gpt-image-2, GPT Image 2, image generation, image editing, image enhancement, resolution increase, upscaling, product shots, mockups, illustrations, visual assets, or wants Codex to create or transform bitmap images without re-explaining the relay base URL or API key location.
---

# GPT Image 2 Relay

Use this skill when GPT Image 2 should run through the user's configured relay instead of the default OpenAI API endpoint.

## Defaults

- Model: `gpt-image-2`
- Primary relay config: `~/.codex/auth.json` for `OPENAI_API_KEY`, plus `~/.codex/config.toml` for the current provider `base_url`
- Fallback relay config: `~/.codex/gpt-image-2-relay-auth.json`, or a named profile file, used only after the primary GPT Image 2 API call fails
- Missing fallback auth files are created as local empty templates when `--init-auth` is used, or after a failed primary API call when fallback is needed
- API key fields: `OPENAI_API_KEY` or `api_key`
- Relay base URL fields: `OPENAI_BASE_URL`, `base_url`, `BASE_URL`, or `url`
- Named profile files: `~/.codex/gpt-image-2-relay-<profile>.json`
- Wrapper script: `scripts/generate.py`
- Underlying CLI: `${CODEX_HOME:-$HOME/.codex}/skills/.system/imagegen/scripts/image_gen.py`
- Output directory: current workspace `$PWD/outputs`
- Python environment: current workspace `$PWD/work/.venv`

Never print, echo, persist, or place API keys in command arguments. The wrapper reads the key and passes it to the child process through environment variables. If an API error includes a key-like value, redact it before showing the user.

## Relay Config

Primary config is tried first:

```text
~/.codex/auth.json
~/.codex/config.toml
```

Fallback config is tried only after the primary GPT Image 2 API call fails. If the file is missing when fallback is needed, the wrapper creates a local template at:

```text
~/.codex/gpt-image-2-relay-auth.json
```

Create or refresh the template without making an API call:

```bash
python "${CODEX_HOME:-$HOME/.codex}/skills/gpt-image-2-relay/scripts/generate.py" --init-auth
```

Fill the template locally:

```json
{
  "_instructions": "Fill OPENAI_API_KEY. Fill OPENAI_BASE_URL if this fallback should use a different relay; leave it empty to reuse ~/.codex/config.toml. Keep this file in ~/.codex and do not commit it.",
  "OPENAI_API_KEY": "",
  "OPENAI_BASE_URL": ""
}
```

Never add filled auth JSON files to the skill folder, workspace, or GitHub repository.

Multiple fallback relay keys can be kept in separate profile files:

```text
~/.codex/gpt-image-2-relay-work.json
~/.codex/gpt-image-2-relay-personal.json
```

Each file uses the same JSON shape:

```json
{
  "OPENAI_API_KEY": "",
  "OPENAI_BASE_URL": ""
}
```

Use a fallback profile with:

```bash
python "${CODEX_HOME:-$HOME/.codex}/skills/gpt-image-2-relay/scripts/generate.py" \
  --profile work \
  --prompt "$PROMPT" \
  --filename "$FILENAME"
```

The primary config still runs first; the profile is tried only if that primary API call fails.

Create an empty profile template with:

```bash
python "${CODEX_HOME:-$HOME/.codex}/skills/gpt-image-2-relay/scripts/generate.py" --init-auth --profile work
```

Alternatively, put multiple fallback profiles in `~/.codex/gpt-image-2-relay-auth.json`:

```json
{
  "profiles": {
    "work": {
      "OPENAI_API_KEY": "",
      "OPENAI_BASE_URL": ""
    },
    "personal": {
      "OPENAI_API_KEY": "",
      "OPENAI_BASE_URL": ""
    }
  }
}
```

## Workflow

1. Use the wrapper script for generation or edits unless the user explicitly asks for lower-level CLI/API details.
2. Run from the current workspace root so outputs land in that workspace's `outputs/` directory.
3. Choose `--quality low` for quick tests or drafts. Use `medium`, `high`, or `auto` for final assets.
4. Use `--size 1024x1024` for fast square tests. For final assets, choose an appropriate GPT Image 2 size such as `1536x1024`, `1024x1536`, `2048x1152`, or `2048x2048`.
5. Save user-facing final images under `$PWD/outputs`, using a descriptive filename.
6. Inspect the generated image before reporting success when the task asks for a final asset.

## Generate

```bash
python "${CODEX_HOME:-$HOME/.codex}/skills/gpt-image-2-relay/scripts/generate.py" \
  --prompt "$PROMPT" \
  --filename "$FILENAME" \
  --size 1024x1024 \
  --quality low
```

The wrapper automatically:

- Creates `$PWD/outputs` and `$PWD/work/.venv` when needed.
- Installs the `openai` Python package into `$PWD/work/.venv` when missing.
- Reads the relay key and base URL from the configured environment/files.
- Calls the bundled imagegen CLI with `--model gpt-image-2`.
- Avoids overwriting existing output files unless `--force` is passed.

## Edit Or Upscale

Pass one or more `--image` paths to edit an existing image. The wrapper then calls the bundled imagegen CLI `edit` command with `--model gpt-image-2`.

For requests like "提高分辨率", "enhance", "upscale", or "make this image sharper", use an edit prompt that preserves the original content:

```bash
python "${CODEX_HOME:-$HOME/.codex}/skills/gpt-image-2-relay/scripts/generate.py" \
  --image "$INPUT_IMAGE" \
  --prompt "Increase the image resolution and clarity while preserving the same subject, composition, colors, identity, and background. Do not add new objects or text." \
  --filename "$OUTPUT_FILENAME" \
  --size 2048x2048 \
  --quality high
```

For edits, prefer `--size` larger than the source when the user asks to increase resolution, while respecting GPT Image 2 size constraints. Do not pass `--input-fidelity` with GPT Image 2.

## Common Options

- `--prompt`: Required unless `--prompt-file` is used.
- `--image`: Existing image path. Repeat for multi-image edits. When present, the wrapper uses the edit endpoint.
- `--mask`: Optional edit mask path for the first input image.
- `--filename`: Filename under `$PWD/outputs`.
- `--out`: Exact output path.
- `--size`: GPT Image 2 size, default `1024x1024`.
- `--quality`: `low`, `medium`, `high`, or `auto`; default `medium`.
- `--use-case`, `--style`, `--composition`, `--lighting`, `--constraints`, `--negative`: Prompt augmentation hints passed through to the underlying imagegen CLI.
- `--dry-run`: Validate command construction without calling the API.
- `--force`: Allow replacing the selected output path.
- `--init-auth`: Create a local empty fallback auth template at `~/.codex/gpt-image-2-relay-auth.json`, or at `~/.codex/gpt-image-2-relay-<profile>.json` with `--profile`, then exit.

## Transparent Backgrounds

Do not request `background=transparent` with `gpt-image-2`; the model does not support that parameter. For simple transparent assets, generate on a flat chroma-key background and remove it locally with the system imagegen helper. Ask before using any model downgrade for true native transparency.

## Failure Handling

- If authentication fails, tell the user the configured relay key appears invalid for the configured relay; do not print the key.
- If fallback config is missing, the wrapper creates an empty local template and tells the user to fill `OPENAI_API_KEY` and `OPENAI_BASE_URL`; do not ask them to put credentials in the GitHub repo.
- If the relay returns `model_not_found`, tell the user the configured relay/account/group does not expose `gpt-image-2`.
- If dependency installation fails, report that `$PWD/work/.venv` could not install `openai`.
- If an output already exists and replacement was not requested, rerun with a unique filename or pass `--force` only when the user explicitly wants replacement.
