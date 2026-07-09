# GPT Image 2 Relay Skill

Codex skill for generating and editing images with `gpt-image-2` through an OpenAI-compatible relay.

The skill wraps Codex's bundled image generation helper, reads relay credentials from local Codex config files, and keeps API keys out of shell history and command arguments.

## What It Does

- Uses `gpt-image-2` for both image generation and image edits.
- Reads the primary relay from the current provider in `~/.codex/config.toml`.
- Supports provider keys from `experimental_bearer_token`, `OPENAI_API_KEY`, `api_key`, or `bearer_token`.
- Normalizes the primary provider `base_url` to an OpenAI-compatible `/v1` endpoint.
- Falls back to local profile files such as `~/.codex/gpt-image-2-relay-auth-work.json` only if the primary call fails.
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
```

If the `base_url` does not end in `/v1`, the wrapper appends `/v1` for the primary GPT Image 2 call.

If the selected provider has no usable API key field, the wrapper falls back to `~/.codex/auth.json` for the primary key:

```json
{
  "OPENAI_API_KEY": "YOUR_RELAY_API_KEY"
}
```

Do not put real credentials in this repository. Keep filled config and auth files under `~/.codex`.

## Optional Fallback Profiles

Fallback profiles are tried only after the primary GPT Image 2 API call fails.

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
  "_instructions": "Fill OPENAI_API_KEY. Fill OPENAI_BASE_URL if this fallback should use a different relay; leave it empty to reuse ~/.codex/config.toml. Keep this file in ~/.codex and do not commit it.",
  "OPENAI_API_KEY": "",
  "OPENAI_BASE_URL": ""
}
```

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

You can also keep multiple fallback profiles inside `~/.codex/gpt-image-2-relay-auth.json`:

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

## Use

Generate an image:

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py \
  --prompt "A red apple on a white background, realistic product photography" \
  --filename apple.png \
  --size 1024x1024 \
  --quality low
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
- `--size`: image size, for example `1024x1024`, `1536x1024`, `1024x1536`, `2048x1152`, or `2048x2048`.
- `--quality`: `low`, `medium`, `high`, or `auto`.
- `--profile`: named fallback profile.
- `--force`: replace an existing output path.

## Troubleshooting

- `model_not_found`: your relay/account/group probably does not expose `gpt-image-2`.
- `AuthenticationError`: check the selected provider token in `~/.codex/config.toml` or the local fallback profile.
- `base_url missing`: set `base_url` in the selected provider table in `~/.codex/config.toml`.
- `imagegen CLI not found`: make sure Codex's bundled system skills are installed at `~/.codex/skills/.system/imagegen`.
- `openai package is missing`: rerun without `--skip-install` so the wrapper can install it into `work/.venv`.

## Security Notes

Never commit API keys, relay credentials, `~/.codex/gpt-image-2-relay-auth*.json`, `.env` files, generated `outputs/`, or workspace `work/` directories. The wrapper passes keys to the child process through environment variables and redacts key-like strings from child output.
