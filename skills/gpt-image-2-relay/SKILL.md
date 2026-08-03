---
name: gpt-image-2-relay
description: Generate or edit raster images through one or multiple configurable OpenAI-compatible relay APIs, using standard GPT Image models or arbitrary relay model IDs and aliases. Use for GPT Image 2, custom or Chinese model IDs, concurrent multi-API prompt distribution, image editing, enhancement, upscaling, product shots, mockups, illustrations, and other bitmap creation or transformation without re-explaining relay credentials.
---

# GPT Image Relay

Use the wrapper for standard GPT Image models and relay-specific model IDs. Keep model IDs and relay parameter values exact; do not rewrite aliases, translate Chinese IDs, or normalize ratio strings.

## Defaults

- Driver: `auto`; known system models use `imagegen`, while every other exact model ID uses `openai-images`
- Model: selected relay config, then `gpt-image-2`
- Single-API behavior is the default. Without `--profiles` or `--profile-count`, inline `profiles` are never called automatically.
- Concurrent multi-API behavior is explicit. Use `--profiles` to choose names or all configured profiles, or `--profile-count` to choose the first N configured profiles.
- In multi-profile mode, repeat `--prompt` and/or `--prompt-file` in the intended order. Assign each prompt once, round-robin, across the selected profiles.
- Only config source: `~/.codex/gpt-image-2-relay-auth.json`; do not read `~/.codex/config.toml`, `~/.codex/auth.json`, or API-key environment variables.
- Default single API: top-level fields in `~/.codex/gpt-image-2-relay-auth.json`.
- Named single API and concurrent APIs: the inline `profiles` object in the same JSON file.
- Missing relay auth JSON is created as a local empty template when `--init-auth` is used or a generation command first needs it.
- JSON auth API key fields: `OPENAI_API_KEY` or `api_key`
- Relay base URL fields: `OPENAI_BASE_URL`, `base_url`, `BASE_URL`, or `url`
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

Read relay credentials and optional image settings only from:

```text
~/.codex/gpt-image-2-relay-auth.json
```

Do not inspect or use `~/.codex/config.toml` or `~/.codex/auth.json` for this skill. Pass relay base URLs through as written.

Create or refresh the template without making an API call:

```bash
python "${CODEX_HOME:-$HOME/.codex}/skills/gpt-image-2-relay/scripts/generate.py" --init-auth
```

Fill the template locally:

```json
{
  "_instructions": "The top-level relay remains the default single API. Fill profiles only for concurrent multi-API generation.",
  "OPENAI_API_KEY": "",
  "OPENAI_BASE_URL": "",
  "driver": "openai-images",
  "model": "YOUR_EXACT_RELAY_MODEL_ID",
  "size": "YOUR_RELAY_SIZE",
  "quality": "high",
  "response_format": "url",
  "output_format": "png",
  "profiles": {
    "relay_1": {
      "OPENAI_API_KEY": "",
      "OPENAI_BASE_URL": ""
    },
    "relay_2": {
      "OPENAI_API_KEY": "",
      "OPENAI_BASE_URL": ""
    },
    "relay_3": {
      "OPENAI_API_KEY": "",
      "OPENAI_BASE_URL": ""
    }
  }
}
```

Treat the `model` and `size` values above as opaque relay values. Examples such as `特惠image2`, `gpt-image-2-4K 高质量线路`, `3:2`, and `21:9` require no code changes. Keep only `OPENAI_API_KEY` and `OPENAI_BASE_URL` in each concurrent profile unless that relay genuinely needs a request-setting override.

Never add filled auth JSON files to the skill folder, workspace, or GitHub repository.

Use the top-level relay by omitting all profile selectors. Use one named inline profile directly with:

```bash
python "${CODEX_HOME:-$HOME/.codex}/skills/gpt-image-2-relay/scripts/generate.py" \
  --profile relay_1 \
  --prompt "$PROMPT" \
  --filename "$FILENAME"
```

Named single-relay and concurrent profiles live inside the same JSON file:

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

The top-level `driver`, `model`, `size`, and other image settings are shared by concurrent profiles. Explicit CLI options override profile-specific settings, which override shared top-level settings, which override built-in defaults.

### Concurrent Multi-API Prompt Distribution

Do not pass a multi-profile option for normal single-API generation. To assign two prompts to an exact two-profile subset:

```bash
python "${CODEX_HOME:-$HOME/.codex}/skills/gpt-image-2-relay/scripts/generate.py" \
  --profiles relay_1,relay_3 \
  --prompt-file "$PROMPT_1" \
  --prompt-file "$PROMPT_2" \
  --filename "$FILENAME"
```

To distribute three prompts across the first two profiles that contain both required credential fields:

```bash
python "${CODEX_HOME:-$HOME/.codex}/skills/gpt-image-2-relay/scripts/generate.py" \
  --profile-count 2 \
  --prompt "$PROMPT_1" \
  --prompt "$PROMPT_2" \
  --prompt "$PROMPT_3" \
  --filename "$FILENAME"
```

The assignment above is `prompt 1 -> relay_1`, `prompt 2 -> relay_2`, and `prompt 3 -> relay_1`.

Use every configured inline profile only when explicitly requested:

```bash
python "${CODEX_HOME:-$HOME/.codex}/skills/gpt-image-2-relay/scripts/generate.py" \
  --profiles all \
  --prompt-file "$PROMPT_1" \
  --prompt-file "$PROMPT_2" \
  --prompt-file "$PROMPT_3" \
  --filename "$FILENAME"
```

Multi-profile mode:

- Requires at least two profiles and does not call the top-level single API.
- Treats every repeated `--prompt` or `--prompt-file` as one ordered prompt task and sends each task exactly once.
- Assigns prompt task `i` to selected profile `(i - 1) % profile_count`. Do not broadcast one prompt to every profile.
- Runs different profile queues concurrently. Run multiple tasks assigned to the same profile sequentially in their original order.
- Leaves extra selected profiles unused when there are fewer prompts than profiles. A single prompt goes only to the first selected profile.
- Writes task- and profile-isolated files such as `image--p001--relay-1.png` and `image--p004--relay-1.png` when multiple prompts are supplied.
- Preserves successful outputs but exits nonzero if any prompt task fails.
- Bills per prompt task, not per selected profile. With five prompts and `--n 2`, up to ten images may be generated and billed.

Resolve single-relay request settings in this order: explicit CLI option, selected relay config, built-in default. Resolve concurrent inline-profile settings in this order: explicit CLI option, selected profile override, shared top-level auth JSON setting, built-in default.

## Workflow

1. Use the wrapper script for generation or edits unless the user explicitly asks for lower-level CLI/API details.
2. Run from the current workspace root so outputs land in that workspace's `outputs/` directory.
3. Choose `--quality low` for quick tests or drafts. Use `medium`, `high`, or `auto` for final assets.
4. Use a size accepted by the selected relay. Standard GPT Image accepts pixel sizes; custom relays may accept ratios or tier-specific values.
5. Save user-facing final images under `$PWD/outputs`, using a descriptive filename.
6. Inspect the generated image before reporting success when the task asks for a final asset.
7. For a requested multi-API run, pass each prompt as a separate repeated `--prompt` or `--prompt-file` option in the intended order. Honor explicit profile names or counts. If the user asks for multiple APIs without a count, default to `--profile-count 2`; use `--profiles all` only when the user explicitly requests every configured API.
8. State that each prompt task is a separate billable request before starting a non-dry multi-API run.

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
  --driver openai-images \
  --model "YOUR_EXACT_RELAY_MODEL_ID" \
  --size "YOUR_RELAY_SIZE" \
  --prompt "$PROMPT" \
  --filename "$FILENAME"
```

The wrapper automatically:

- Creates `$PWD/outputs` and `$PWD/work/.venv` when needed.
- Installs the `openai` Python package only when the `imagegen` driver needs it.
- Reads the default relay or selected inline profile only from `~/.codex/gpt-image-2-relay-auth.json`.
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

- `--prompt`: Required unless `--prompt-file` is used. Repeat to add ordered tasks in multi-profile mode.
- `--prompt-file`: Read a prompt from a file. Repeat to add ordered tasks in multi-profile mode; it may be interleaved with `--prompt`.
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
- `--profile`: Use one named inline profile instead of the top-level default API.
- `--profiles`: Distribute ordered prompt tasks round-robin across comma-separated/repeated inline profile names, or pass `all`.
- `--profile-count`: Distribute ordered prompt tasks round-robin across the first N fully configured inline profiles; N must be at least 2.
- `--n`: Images requested per prompt task; default `1`.
- `--use-case`, `--style`, `--composition`, `--lighting`, `--constraints`, `--negative`: Prompt augmentation hints. The direct driver also forwards `style` as a native relay field.
- `--dry-run`: Validate command construction without calling the API.
- `--force`: Allow replacing the selected output path.
- `--init-auth`: Create the local empty template at `~/.codex/gpt-image-2-relay-auth.json`, then exit.

## Transparent Backgrounds

Do not request `background=transparent` with standard `gpt-image-2`; the system driver rejects it. The direct driver passes `background` unchanged, so use transparency only when the selected relay model documents support. For simple unsupported assets, generate on a flat chroma-key background and remove it locally.

## Failure Handling

- If authentication fails, tell the user the configured relay key appears invalid for the configured relay; do not print the key.
- If the relay auth JSON is missing, the wrapper creates an empty local template and tells the user to fill `OPENAI_API_KEY` and `OPENAI_BASE_URL`; do not ask them to put credentials in the GitHub repo.
- If the relay returns `model_not_found`, report the exact configured model ID without silently replacing it.
- If dependency installation fails, report that `$PWD/work/.venv` could not install `openai`.
- If a direct relay returns no `url` or `b64_json`, report the response-shape incompatibility.
- If an output already exists and replacement was not requested, rerun with a unique filename or pass `--force` only when the user explicitly wants replacement.
- If one concurrent prompt task fails, allow all other queued tasks to finish, keep their successful outputs, report the per-task summary, and treat the overall command as failed.
