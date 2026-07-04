# GPT Image 2 Relay Skill

Codex skill for generating and editing images with `gpt-image-2` through an OpenAI-compatible relay.

## Install From GitHub

After pushing this folder to a GitHub repository, install the skill with:

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --url https://github.com/<owner>/<repo>/tree/main/skills/gpt-image-2-relay
```

Restart Codex after installation.

## Configure

By default, the skill first uses your normal Codex config:

```text
~/.codex/auth.json
~/.codex/config.toml
```

If that primary GPT Image 2 API call fails, the wrapper can retry with a fallback relay config.

Create:

```text
~/.codex/gpt-image-2-relay-auth.json
```

with:

```json
{
  "OPENAI_API_KEY": "sk-...",
  "OPENAI_BASE_URL": "https://your-relay.example/v1"
}
```

You can still override the primary run with environment variables:

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://your-relay.example/v1"
```

or configure `~/.codex/config.toml` for the primary run:

```toml
model_provider = "custom"

[model_providers.custom]
base_url = "https://your-relay.example/v1"
```

Do not commit API keys or private relay credentials.

## Multiple Relay Profiles

Use separate fallback files when you have multiple relay keys:

```text
~/.codex/gpt-image-2-relay-work.json
~/.codex/gpt-image-2-relay-personal.json
```

Each file uses:

```json
{
  "OPENAI_API_KEY": "sk-...",
  "OPENAI_BASE_URL": "https://your-relay.example/v1"
}
```

Then select one as fallback with:

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py \
  --profile work \
  --prompt "A red apple on a white background" \
  --filename apple.png
```

The primary `~/.codex/auth.json` + `~/.codex/config.toml` run still happens first. The selected profile is retried only if the primary GPT Image 2 API call fails.

You can also keep fallback profiles inside `~/.codex/gpt-image-2-relay-auth.json`:

```json
{
  "profiles": {
    "work": {
      "OPENAI_API_KEY": "sk-...",
      "OPENAI_BASE_URL": "https://work-relay.example/v1"
    },
    "personal": {
      "OPENAI_API_KEY": "sk-...",
      "OPENAI_BASE_URL": "https://personal-relay.example/v1"
    }
  }
}
```

## Use

Generate:

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py \
  --prompt "A red apple on a white background, realistic product photography" \
  --filename apple.png \
  --size 1024x1024 \
  --quality low
```

Edit or upscale:

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py \
  --image input.png \
  --prompt "Increase the image resolution and clarity while preserving the same subject, composition, colors, identity, and background. Do not add new objects or text." \
  --filename enhanced.png \
  --size 2048x2048 \
  --quality high
```
