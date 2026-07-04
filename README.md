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

Provide an API key in one of these ways:

```bash
export OPENAI_API_KEY="sk-..."
```

or create:

```text
~/.codex/gpt-image-2-relay-auth.json
```

with:

```json
{
  "OPENAI_API_KEY": "sk-..."
}
```

Provide the relay base URL in one of these ways:

```bash
export OPENAI_BASE_URL="https://your-relay.example/v1"
```

or configure `~/.codex/config.toml`:

```toml
model_provider = "custom"

[model_providers.custom]
base_url = "https://your-relay.example/v1"
```

Do not commit API keys or private relay credentials.

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
