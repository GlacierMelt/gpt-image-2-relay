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

## Use in Codex Chat

Select the `gpt-image-2-relay` skill in Codex or include `$gpt-image-2-relay` in the message. Describe the profiles, ordered prompts, and `n` in natural language; Codex will call the wrapper, so shell commands are not required.

Start with a no-cost routing check:

```text
使用 $gpt-image-2-relay 做一次 dry-run，不要真实调用 API。

选择 profiles：relay_1、relay_2、relay_3，n=1。
按顺序分配以下提示词，每段只发送给一个 API，不要广播：
1. 雨夜东京街角的微型拉面店，电影级摄影
2. 透明 ESC 键帽中的微型森林工作室，写实微距
3. 火星基地窗边的宇航员与盆栽，柔和晨光

请显示提示词到 API 的分配、请求数量和预计输出文件名。
```

Expected routing:

```text
p001 -> relay_1
p002 -> relay_2
p003 -> relay_3
```

To run the same case with real generation, replace the first sentence with:

```text
使用 $gpt-image-2-relay 真实生图。开始前先报告分配关系和总请求数，然后生成并检查全部结果。
```

Test more prompts than APIs with:

```text
使用 $gpt-image-2-relay 做一次 dry-run，不要真实调用 API。
只使用 relay_1 和 relay_2，n=1。
将下面五段提示词按顺序轮询分配，每段只请求一次：
1. 白色背景上的透明玻璃相机，产品摄影
2. 深海中的发光水下车站，电影概念设计
3. 秋日森林里的现代图书馆，建筑摄影
4. 月球表面的复古咖啡车，写实摄影
5. 巨型花朵中的微型钟表工坊，微距摄影
请显示分配关系和总请求数。
```

Expected routing is `1 -> relay_1`, `2 -> relay_2`, `3 -> relay_1`, `4 -> relay_2`, and `5 -> relay_1`.

Use these expected outcomes when testing from Codex:

| Case | Profiles | Prompts | `n` | Expected API requests | Expected behavior |
| --- | --- | ---: | ---: | ---: | --- |
| Default single API | none | 1 | 1 | 1 | Use only the top-level API |
| One-to-one distribution | 3 | 3 | 1 | 3 | Assign one distinct prompt to each profile |
| More prompts than APIs | 2 | 5 | 1 | 5 | Assign `A, B, A, B, A`; send every prompt once |
| Fewer prompts than APIs | 3 | 2 | 1 | 2 | Leave the third profile unused |
| Two images per prompt | 3 | 3 | 2 | 3 | Send three requests with `n=2`; expect up to six images |

`n=2` means two requested images for each prompt task. It does not mean two prompts per API and does not change profile assignment. Before a real multi-API run, Codex should report that every prompt task is a separate billable request.

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
