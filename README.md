# GPT Image Relay Skill

Codex skill for generating and editing images through configurable OpenAI-compatible relay APIs. It supports standard GPT Image models, arbitrary relay model IDs, direct image generations and edits, and concurrent multi-API prompt distribution.

## What It Does

- Selects `imagegen` for known system models and `openai-images` for custom relay models.
- Passes exact relay `model`, `size`, and `quality` values through unchanged.
- Handles URL and Base64 image responses and multipart image edits.
- Reads relay credentials only from `~/.codex/gpt-image-2-relay-auth.json`.
- Keeps the top-level fields as the default single API and uses inline `profiles` only when explicitly selected.
- Distributes repeated prompts across selected profiles without broadcasting one prompt to every API.
- Writes generated assets to the current workspace's `outputs/` directory.

## Install

Install directly from this GitHub repository:

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --url https://github.com/GlacierMelt/gpt-image-2-relay/tree/main/skills/gpt-image-2-relay
```

Restart Codex after installation so the skill is loaded. To update later, run the same command again.

## Configure

The only configuration file is:

```text
~/.codex/gpt-image-2-relay-auth.json
```

Create an empty template without making an API call:

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py --init-auth
```

Fill the top-level default API and any profiles locally:

```json
{
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

Each profile normally needs only `OPENAI_API_KEY` and `OPENAI_BASE_URL`. Keep this file outside the repository and never commit it. The wrapper does not read `~/.codex/config.toml`, `~/.codex/auth.json`, or API-key environment variables.

Model IDs and size values are opaque relay values. Custom values such as `特惠image2`, `gpt-image-2-4K 高质量线路`, `3:2`, and `21:9` require no code changes.

## Single API

Omit profile selectors to use the top-level default API:

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py \
  --prompt "A red apple on a white background, realistic product photography" \
  --filename apple.png \
  --quality low
```

Use one named inline profile directly:

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py \
  --profile relay_1 \
  --prompt "A cinematic product photograph" \
  --filename product.png
```

## Multiple Prompts and APIs

Repeat `--prompt` or `--prompt-file` in the intended order. Each prompt is sent exactly once and assigned round-robin to the selected profiles.

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py \
  --profiles relay_1,relay_2,relay_3 \
  --prompt "A rainy Tokyo alley at night" \
  --prompt "A transparent keycap containing a miniature greenhouse" \
  --prompt "A Mars base at sunrise" \
  --filename batch.png
```

The assignment is `prompt 1 -> relay_1`, `prompt 2 -> relay_2`, and `prompt 3 -> relay_3`. With five prompts and two profiles, the assignment is `1 -> relay_1`, `2 -> relay_2`, `3 -> relay_1`, `4 -> relay_2`, `5 -> relay_1`.

Different profile queues run concurrently. Multiple prompts assigned to the same profile run sequentially in input order. If there are fewer prompts than selected profiles, unused profiles are not called. One prompt is sent only to the first selected profile; it is never broadcast automatically.

When multiple prompts are supplied, outputs include both the prompt index and profile, for example `batch--p001--relay-1.png`. `--n` controls images per prompt task and defaults to `1`; it does not change prompt assignment.

Use `--profile-count N` to select the first N configured profiles, or `--profiles all` only when every configured profile is wanted. Multi-profile runs require at least two selected profiles and do not call the top-level default API.

## Edit or Upscale

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py \
  --image input.png \
  --prompt "Increase resolution and clarity while preserving the subject, composition, colors, identity, and background." \
  --filename enhanced.png \
  --size 2048x2048 \
  --quality high
```

## Validation

Run the local relay simulation suite without credentials or paid API calls:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

Run a no-call command construction check with `--dry-run`.

## Security

Never commit API keys, relay credentials, `~/.codex/gpt-image-2-relay-auth*.json`, `.env` files, generated `outputs/`, or workspace `work/` directories. The wrapper passes keys to child processes without putting them in command arguments and redacts key-like values from errors.
