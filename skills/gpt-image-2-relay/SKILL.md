---
name: gpt-image-2-relay
description: Generate or edit raster images through configurable OpenAI-compatible relay drivers, using standard GPT Image models or arbitrary relay model IDs and aliases. Use for GPT Image 2, custom or Chinese model IDs, image generation, image editing, enhancement, upscaling, product shots, mockups, illustrations, and other bitmap creation or transformation without re-explaining relay credentials.
---

# GPT Image Relay

Use the wrapper for standard GPT Image models and relay-specific model IDs. Keep model IDs and relay parameter values exact; do not rewrite aliases, translate Chinese IDs, or normalize ratio strings.

## Defaults

- Driver: `auto`; known system models use `imagegen`, while every other exact model ID uses `openai-images`
- Model: selected relay config, then `gpt-image-2`
- Primary relay config: `~/.codex/config.toml` current provider for `base_url` and `experimental_bearer_token`; `~/.codex/auth.json` is used only if the provider has no usable API key
- Primary `base_url` is normalized for GPT Image 2 calls: if it does not end in `/v1`, the wrapper appends `/v1`
- Fallback relay config: `~/.codex/gpt-image-2-relay-auth.json`, or a named profile file, used only after the primary GPT Image 2 API call fails
- Missing fallback auth files are created as local empty templates when `--init-auth` is used, or after a failed primary API call when fallback is needed
- Primary provider API key fields: `experimental_bearer_token`, `OPENAI_API_KEY`, `api_key`, or `bearer_token`
- JSON auth API key fields: `OPENAI_API_KEY` or `api_key`
- Relay base URL fields: `OPENAI_BASE_URL`, `base_url`, `BASE_URL`, or `url`
- Named profile files: `~/.codex/gpt-image-2-relay-auth-<profile>.json`
- Wrapper script: `scripts/generate.py`
- Standard driver CLI: `${CODEX_HOME:-$HOME/.codex}/skills/.system/imagegen/scripts/image_gen.py`
- Output directory: current workspace `$PWD/outputs`
- Python environment: current workspace `$PWD/work/.venv`

Never print, echo, persist, or place API keys in command arguments. The wrapper reads the key and passes it to the child process through environment variables. If an API error includes a key-like value, redact it before showing the user.

## Drivers

- `auto`: Use `imagegen` only for known system model IDs. Use `openai-images` for every other ID, including custom IDs that begin with `gpt-image-`.
- `imagegen`: Use the bundled system CLI and its strict GPT Image validation.
- `openai-images`: Call `/images/generations` or `/images/edits` directly. Pass `model`, `size`, `quality`, and supported optional fields unchanged. Accept URL and Base64 image responses.

Set `driver` in a relay config or pass `--driver`. Prefer explicit `openai-images` for custom relays. Do not add individual model IDs to the wrapper; model support is determined by the selected relay.

## Relay Config

Primary config is tried first. The wrapper reads the selected provider from `~/.codex/config.toml`, uses that provider's `experimental_bearer_token` when present, and normalizes the provider `base_url` to an OpenAI-compatible `/v1` root for GPT Image 2:

```text
~/.codex/config.toml
~/.codex/auth.json  # fallback only when the provider has no API key field
```

Fallback config is tried only after the primary GPT Image 2 API call fails. Explicit fallback base URLs are passed through as written; if a fallback profile omits a base URL, it reuses the normalized primary base URL. If the file is missing when fallback is needed, the wrapper creates a local template at:

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
  "_instructions": "Fill relay credentials and optional image settings. Keep this file in ~/.codex and do not commit it.",
  "OPENAI_API_KEY": "",
  "OPENAI_BASE_URL": "",
  "driver": "openai-images",
  "model": "YOUR_EXACT_RELAY_MODEL_ID",
  "size": "YOUR_RELAY_SIZE",
  "quality": "high",
  "response_format": "url",
  "output_format": "png"
}
```

Treat the `model` and `size` values above as opaque relay values. Examples such as `特惠image2`, `gpt-image-2-4K 高质量线路`, `3:2`, and `21:9` require no code changes.

Never add filled auth JSON files to the skill folder, workspace, or GitHub repository.

Multiple fallback relay keys can be kept in separate profile files:

```text
~/.codex/gpt-image-2-relay-auth-work.json
~/.codex/gpt-image-2-relay-auth-personal.json
```

Each file uses the same JSON shape:

```json
{
  "OPENAI_API_KEY": "",
  "OPENAI_BASE_URL": "",
  "driver": "openai-images",
  "model": "YOUR_EXACT_RELAY_MODEL_ID"
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

Use the default relay config or a named profile directly, without first calling the primary provider:

```bash
python "${CODEX_HOME:-$HOME/.codex}/skills/gpt-image-2-relay/scripts/generate.py" \
  --use-profile \
  --profile work \
  --prompt "$PROMPT" \
  --filename "$FILENAME"
```

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
      "OPENAI_BASE_URL": "",
      "driver": "openai-images",
      "model": "YOUR_EXACT_RELAY_MODEL_ID",
      "size": "3:2"
    },
    "personal": {
      "OPENAI_API_KEY": "",
      "OPENAI_BASE_URL": ""
    }
  }
}
```

For the primary provider in `~/.codex/config.toml`, use optional `image_` fields without changing chat-model settings:

```toml
[model_providers.custom]
base_url = "https://relay.example/v1"
experimental_bearer_token = "..."
image_driver = "openai-images"
image_model = "YOUR_EXACT_RELAY_MODEL_ID"
image_size = "3:2"
image_quality = "high"
image_response_format = "url"
image_output_format = "png"
```

Resolve request settings in this order: explicit CLI option, selected relay config, built-in default.

## Workflow

1. Use the wrapper script for generation or edits unless the user explicitly asks for lower-level CLI/API details.
2. Run from the current workspace root so outputs land in that workspace's `outputs/` directory.
3. Choose `--quality low` for quick tests or drafts. Use `medium`, `high`, or `auto` for final assets.
4. Use a size accepted by the selected relay. Standard GPT Image accepts pixel sizes; custom relays may accept ratios or tier-specific values.
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

Generate through a custom relay while passing relay-specific values unchanged:

```bash
python "${CODEX_HOME:-$HOME/.codex}/skills/gpt-image-2-relay/scripts/generate.py" \
  --use-profile \
  --driver openai-images \
  --model "YOUR_EXACT_RELAY_MODEL_ID" \
  --size "YOUR_RELAY_SIZE" \
  --prompt "$PROMPT" \
  --filename "$FILENAME"
```

The wrapper automatically:

- Creates `$PWD/outputs` and `$PWD/work/.venv` when needed.
- Installs the `openai` Python package only when the `imagegen` driver needs it.
- Reads the primary relay key and base URL from the current Codex provider in `~/.codex/config.toml`, then falls back to `~/.codex/auth.json` for the primary key only when needed.
- Selects a driver per relay attempt and passes custom model IDs unchanged through `openai-images`.
- Downloads temporary URL responses immediately or decodes inline Base64 responses.
- Avoids overwriting existing output files unless `--force` is passed.

## Edit Or Upscale

Pass one or more `--image` paths to edit an existing image. The selected driver calls its corresponding edit endpoint.

For requests like "提高分辨率", "enhance", "upscale", or "make this image sharper", use an edit prompt that preserves the original content:

```bash
python "${CODEX_HOME:-$HOME/.codex}/skills/gpt-image-2-relay/scripts/generate.py" \
  --image "$INPUT_IMAGE" \
  --prompt "Increase the image resolution and clarity while preserving the same subject, composition, colors, identity, and background. Do not add new objects or text." \
  --filename "$OUTPUT_FILENAME" \
  --size 2048x2048 \
  --quality high
```

For edits, prefer a relay-supported size larger than the source when the user asks to increase resolution. The `openai-images` driver sends multipart requests and supports up to 8 input images totaling 40 MB. Do not pass `--input-fidelity` with GPT Image 2.

## Common Options

- `--prompt`: Required unless `--prompt-file` is used.
- `--image`: Existing image path. Repeat for multi-image edits. When present, the wrapper uses the edit endpoint.
- `--mask`: Optional edit mask path for the first input image.
- `--filename`: Filename under `$PWD/outputs`.
- `--out`: Exact output path.
- `--driver`: `auto`, `imagegen`, or `openai-images`.
- `--model`: Exact model ID. CLI values override relay configuration.
- `--size`: Exact relay size or ratio; default `1024x1024`.
- `--quality`: Exact relay quality value; default `medium`.
- `--response-format`: `url` or `b64_json` for `openai-images`.
- `--background`, `--upscale`, `--output-format`, `--output-compression`, `--moderation`: Optional relay fields.
- `--extra-json`: Additional JSON object for forward-compatible direct-relay fields. Core fields such as `model` and `prompt` remain authoritative.
- `--use-profile`: Use the selected profile directly instead of trying the primary provider first.
- `--use-case`, `--style`, `--composition`, `--lighting`, `--constraints`, `--negative`: Prompt augmentation hints. The direct driver also forwards `style` as a native relay field.
- `--dry-run`: Validate command construction without calling the API.
- `--force`: Allow replacing the selected output path.
- `--init-auth`: Create a local empty fallback auth template at `~/.codex/gpt-image-2-relay-auth.json`, or at `~/.codex/gpt-image-2-relay-auth-<profile>.json` with `--profile`, then exit.

## Transparent Backgrounds

Do not request `background=transparent` with standard `gpt-image-2`; the system driver rejects it. The direct driver passes `background` unchanged, so use transparency only when the selected relay model documents support. For simple unsupported assets, generate on a flat chroma-key background and remove it locally.

## Failure Handling

- If authentication fails, tell the user the configured relay key appears invalid for the configured relay; do not print the key.
- If fallback config is missing, the wrapper creates an empty local template and tells the user to fill `OPENAI_API_KEY` and `OPENAI_BASE_URL`; do not ask them to put credentials in the GitHub repo.
- If the relay returns `model_not_found`, report the exact configured model ID without silently replacing it.
- If dependency installation fails, report that `$PWD/work/.venv` could not install `openai`.
- If a direct relay returns no `url` or `b64_json`, report the response-shape incompatibility.
- If an output already exists and replacement was not requested, rerun with a unique filename or pass `--force` only when the user explicitly wants replacement.
