# GPT Image Relay Skill

Codex skill for generating and editing images through configurable OpenAI-compatible relay drivers. It supports standard GPT Image models and arbitrary relay model IDs, including custom or Chinese aliases.

The skill uses Codex's bundled image helper for known system models and a direct `/images/generations` or `/images/edits` driver for relay-specific models. It reads credentials from local Codex config files and keeps API keys out of shell history and command arguments.

## What It Does

- Selects `imagegen` or `openai-images` per relay request.
- Passes arbitrary `model`, `size`, and `quality` values to direct relays unchanged.
- Handles URL and Base64 image responses, plus multipart image edits.
- Reads the primary relay from the current provider in `~/.codex/config.toml`.
- Supports provider keys from `experimental_bearer_token`, `OPENAI_API_KEY`, `api_key`, or `bearer_token`.
- Normalizes the primary provider `base_url` to an OpenAI-compatible `/v1` endpoint.
- Falls back to local profile files such as `~/.codex/gpt-image-2-relay-auth-work.json` if the primary call fails, or uses one directly with `--use-profile`.
- Writes generated assets to the current workspace's `outputs/` directory by default.
- Creates and uses a workspace-local Python virtual environment at `work/.venv`.

## Install

Install directly from this GitHub repository:

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --url https://github.com/GlacierMelt/gpt-image-2-relay/tree/main/skills/gpt-image-2-relay
```

Restart Codex after installation so the skill is loaded.

You can also install with explicit repo/path arguments:

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo GlacierMelt/gpt-image-2-relay \
  --path skills/gpt-image-2-relay
```

To update later, rerun the same install command and restart Codex.

## Configure Primary Relay

The wrapper first uses the selected provider in `~/.codex/config.toml`:

```toml
model_provider = "my-relay"

[model_providers.my-relay]
base_url = "https://your-relay.example"
experimental_bearer_token = "YOUR_RELAY_API_KEY"
image_driver = "openai-images"
image_model = "YOUR_EXACT_RELAY_MODEL_ID"
image_size = "YOUR_RELAY_SIZE"
image_quality = "high"
image_response_format = "url"
image_output_format = "png"
```

The `image_` fields are optional and do not change the provider's chat-model settings. Explicit CLI options override these fields. If the primary `base_url` does not end in `/v1`, the wrapper appends `/v1`.

If the selected provider has no usable API key field, the wrapper falls back to `~/.codex/auth.json` for the primary key:

```json
{
  "OPENAI_API_KEY": "YOUR_RELAY_API_KEY"
}
```

Do not put real credentials in this repository. Keep filled config and auth files under `~/.codex`.

## Relay Profiles

Profiles are tried after the primary image call fails by default. Add `--use-profile` to skip the primary provider and use a profile directly.

Create a local fallback template:

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py --init-auth
```

That creates:

```text
~/.codex/gpt-image-2-relay-auth.json
```

Fill it locally:

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

The wrapper treats model IDs and size values as opaque relay strings. IDs such as `特惠image2` and `gpt-image-2-4K 高质量线路`, plus sizes such as `3:2` and `21:9`, require no code changes.

Create a named fallback profile:

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py --init-auth --profile work
```

That creates:

```text
~/.codex/gpt-image-2-relay-auth-work.json
```

Use the profile:

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py \
  --profile work \
  --prompt "A red apple on a white background, realistic product photography" \
  --filename apple.png
```

Use it directly without calling the primary provider first:

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py \
  --use-profile \
  --profile work \
  --prompt "A red apple on a white background, realistic product photography" \
  --filename apple.png
```

You can also keep multiple fallback profiles inside `~/.codex/gpt-image-2-relay-auth.json`:

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

## Use

Generate an image:

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py \
  --prompt "A red apple on a white background, realistic product photography" \
  --filename apple.png \
  --size 1024x1024 \
  --quality low
```

Generate with an arbitrary relay model ID and relay-specific size:

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py \
  --use-profile \
  --driver openai-images \
  --model "YOUR_EXACT_RELAY_MODEL_ID" \
  --size "YOUR_RELAY_SIZE" \
  --prompt "A cinematic product photograph" \
  --filename product.png
```

Edit or upscale an existing image:

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py \
  --image input.png \
  --prompt "Increase the image resolution and clarity while preserving the same subject, composition, colors, identity, and background. Do not add new objects or text." \
  --filename enhanced.png \
  --size 2048x2048 \
  --quality high
```

Check command construction without calling the API:

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py \
  --prompt "Smoke test image" \
  --filename smoke.png \
  --quality low \
  --dry-run
```

## Useful Options

- `--prompt` or `--prompt-file`: generation/edit instruction.
- `--image`: input image path for edits; repeat for multi-image edits.
- `--mask`: optional mask path for the first input image.
- `--filename`: filename under the workspace `outputs/` directory.
- `--out`: exact output path.
- `--driver`: `auto`, `imagegen`, or `openai-images`.
- `--model`: exact relay model ID.
- `--size`: exact pixel size, ratio, or relay-specific size value.
- `--quality`: exact relay quality value.
- `--response-format`: `url` or `b64_json` for the direct driver.
- `--background`, `--upscale`, `--output-format`, `--output-compression`, `--moderation`: optional relay fields.
- `--extra-json`: forward-compatible JSON fields for direct requests.
- `--profile`: named fallback profile.
- `--use-profile`: use the selected profile directly.
- `--force`: replace an existing output path.

## Test

Run the local relay simulation suite without credentials or paid API calls:

```bash
python -m unittest -v tests/test_generate.py
```

## Troubleshooting

- `model_not_found`: the selected relay does not expose the exact configured model ID.
- `AuthenticationError`: check the selected provider token in `~/.codex/config.toml` or the local fallback profile.
- `base_url missing`: set `base_url` in the selected provider table in `~/.codex/config.toml`.
- `imagegen CLI not found`: make sure Codex's bundled system skills are installed at `~/.codex/skills/.system/imagegen`.
- `openai package is missing`: rerun without `--skip-install` so the wrapper can install it into `work/.venv`.
- `relay response did not contain url or b64_json`: the selected endpoint uses an unsupported response shape.

## Security Notes

Never commit API keys, relay credentials, `~/.codex/gpt-image-2-relay-auth*.json`, `.env` files, generated `outputs/`, or workspace `work/` directories. The wrapper passes keys to the standard driver through environment variables, keeps direct-driver credentials in process memory, and redacts key-like strings from errors.
