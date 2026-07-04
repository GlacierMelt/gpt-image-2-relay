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

If that primary GPT Image 2 API call fails, the wrapper can retry with a fallback relay config. If the fallback file is missing when fallback is needed, the wrapper creates a local empty template automatically and tells you where to fill it.

Create the template anytime with:

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py --init-auth
```

Default fallback file:

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

Do not commit API keys or private relay credentials. Keep filled auth JSON files in `~/.codex`, not inside this GitHub repo.

## Multiple Relay Profiles

Use separate fallback files when you have multiple relay keys:

```text
~/.codex/gpt-image-2-relay-work.json
~/.codex/gpt-image-2-relay-personal.json
```

Each file uses:

```json
{
  "_instructions": "Fill OPENAI_API_KEY. Fill OPENAI_BASE_URL if this fallback should use a different relay; leave it empty to reuse ~/.codex/config.toml. Keep this file in ~/.codex and do not commit it.",
  "OPENAI_API_KEY": "",
  "OPENAI_BASE_URL": ""
}
```

Create an empty profile template with:

```bash
python ~/.codex/skills/gpt-image-2-relay/scripts/generate.py --init-auth --profile work
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
