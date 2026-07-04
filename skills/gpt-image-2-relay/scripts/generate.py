#!/usr/bin/env python3
"""Generate or edit images with the bundled imagegen CLI through the user's relay.

This wrapper intentionally keeps API keys out of command-line arguments and
redacts key-like strings from child process output.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_AUTH_JSON = Path.home() / ".codex" / "auth.json"
DEFAULT_IMAGE_AUTH_JSON = Path.home() / ".codex" / "gpt-image-2-relay-auth.json"
DEFAULT_CONFIG_TOML = Path.home() / ".codex" / "config.toml"
DEFAULT_MODEL = "gpt-image-2"
KEY_RE = re.compile(r"sk-[A-Za-z0-9_-]{8,}")
BASE_URL_KEYS = ("OPENAI_BASE_URL", "base_url", "BASE_URL", "url")
AUTH_TEMPLATE_INSTRUCTIONS = (
    "Fill OPENAI_API_KEY. Fill OPENAI_BASE_URL if this fallback should use a "
    "different relay; leave it empty to reuse ~/.codex/config.toml. Keep this "
    "file in ~/.codex and do not commit it."
)


def fail(message: str, code: int = 1) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def sanitize(text: str, api_key: str | None = None) -> str:
    if api_key:
        text = text.replace(api_key, "sk-<redacted>")
    return KEY_RE.sub("sk-<redacted>", text)


def read_api_key(path: Path) -> str:
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        fail(f"auth file not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"auth file is not valid JSON: {path}: {exc}")
    value = data.get("OPENAI_API_KEY")
    if not isinstance(value, str) or not value.strip():
        fail(f"OPENAI_API_KEY missing in {path}")
    return value.strip()


def read_json_object(path: Path, required: bool = False) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        if required:
            fail(f"auth file not found: {path}")
        return {}
    except json.JSONDecodeError as exc:
        fail(f"auth file is not valid JSON: {path}: {exc}")
    if not isinstance(data, dict):
        fail(f"auth file must contain a JSON object: {path}")
    return data


def profile_file(base_path: Path, profile: str) -> Path:
    return base_path.with_name(f"{base_path.stem}-{profile}{base_path.suffix}")


def extract_profile(data: dict[str, Any], profile: str, source: Path) -> dict[str, Any]:
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        return {}
    value = profiles.get(profile)
    if value is None:
        return {}
    if not isinstance(value, dict):
        fail(f"profile {profile!r} in {source} must be a JSON object")
    return value


def write_auth_template(path: Path) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    template = {
        "_instructions": AUTH_TEMPLATE_INSTRUCTIONS,
        "OPENAI_API_KEY": "",
        "OPENAI_BASE_URL": "",
    }
    path.write_text(json.dumps(template, indent=2) + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return True


def fail_with_auth_template(path: Path, reason: str, profile: str | None = None) -> None:
    created = write_auth_template(path)
    target = f"fallback relay profile {profile!r}" if profile else "fallback relay config"
    action = "Created" if created else "Use"
    fail(
        f"{reason}. {action} {target} template at {path}. "
        "Fill OPENAI_API_KEY and OPENAI_BASE_URL with your relay key/base URL, then rerun. "
        "Keep this file outside the GitHub repo; do not commit private credentials."
    )


def resolve_api_key(config: dict[str, Any], allow_env: bool = True, source: str = "selected relay config") -> str:
    env_key = os.environ.get("OPENAI_API_KEY") if allow_env else None
    if env_key:
        return env_key.strip()
    value = config.get("OPENAI_API_KEY") or config.get("api_key")
    if not isinstance(value, str) or not value.strip():
        fail(
            f"OPENAI_API_KEY missing in {source}. "
            "Fill that local auth file with your relay key/base URL, then rerun."
        )
    return value.strip()


def base_url_from_config(config: dict[str, Any]) -> str | None:
    for key in BASE_URL_KEYS:
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve_relay_auth_config(
    image_auth_path: Path,
    profile: str | None,
    create_missing: bool = False,
) -> tuple[dict[str, Any], str | None]:
    if profile:
        selected_profile_path = profile_file(image_auth_path, profile)
        if selected_profile_path.exists():
            return read_json_object(selected_profile_path, required=True), str(selected_profile_path)
        default_data = read_json_object(image_auth_path)
        inline_profile = extract_profile(default_data, profile, image_auth_path)
        if inline_profile:
            return inline_profile, f"{image_auth_path} profiles.{profile}"
        if create_missing:
            fail_with_auth_template(
                selected_profile_path,
                f"profile {profile!r} not found. Expected {selected_profile_path} "
                f"or profiles.{profile} in {image_auth_path}",
                profile=profile,
            )
        return {}, None
    if image_auth_path.exists():
        return read_json_object(image_auth_path, required=True), str(image_auth_path)
    if create_missing:
        fail_with_auth_template(image_auth_path, "fallback relay config not found")
    return {}, None


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value[0] in {"'", '"'}:
        quote = value[0]
        out = []
        escaped = False
        for ch in value[1:]:
            if escaped:
                out.append(ch)
                escaped = False
            elif ch == "\\" and quote == '"':
                escaped = True
            elif ch == quote:
                return "".join(out)
            else:
                out.append(ch)
        return "".join(out)
    if "#" in value:
        value = value.split("#", 1)[0].strip()
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return value


def _load_toml(path: Path) -> dict[str, Any]:
    text = path.read_text(errors="replace")
    try:
        import tomllib  # type: ignore

        return tomllib.loads(text)
    except ModuleNotFoundError:
        pass
    except Exception:
        pass

    root: dict[str, Any] = {}
    current: dict[str, Any] = root
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = root
            for part in line[1:-1].split("."):
                part = part.strip().strip('"').strip("'")
                current = current.setdefault(part, {})
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*=\s*(.+)$", line)
        if match:
            current[match.group(1)] = _parse_scalar(match.group(2))
    return root


def read_base_url(path: Path, provider: str | None) -> str:
    try:
        data = _load_toml(path)
    except FileNotFoundError:
        fail(f"config file not found: {path}")

    selected = provider or data.get("model_provider") or "custom"
    providers = data.get("model_providers")
    if isinstance(providers, dict):
        table = providers.get(str(selected))
        if isinstance(table, dict):
            value = table.get("base_url")
            if isinstance(value, str) and value.strip():
                return value.strip()

    fail(f"base_url missing for model provider {selected!r} in {path}")


def ensure_runtime(workspace: Path, requested_python: str | None, skip_install: bool) -> Path:
    if requested_python:
        py = Path(requested_python).expanduser()
        if not py.exists() and os.sep not in requested_python:
            found = shutil.which(requested_python)
            if found:
                return Path(found)
        if not py.exists():
            fail(f"requested Python does not exist: {py}")
        return py

    venv_dir = workspace / "work" / ".venv"
    py = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not py.exists():
        venv_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    check = subprocess.run([str(py), "-c", "import openai"], capture_output=True, text=True)
    if check.returncode != 0:
        if skip_install:
            fail(f"openai package is missing in {venv_dir}; rerun without --skip-install")
        subprocess.run([str(py), "-m", "pip", "install", "openai"], check=True)
    return py


def default_cli_path() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    return codex_home / "skills" / ".system" / "imagegen" / "scripts" / "image_gen.py"


def slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48].strip("-") or "image"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    fail(f"could not find an unused filename near {path}")


def choose_output(args: argparse.Namespace, workspace: Path) -> Path:
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else workspace / "outputs"
    output_dir = output_dir if output_dir.is_absolute() else workspace / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.out:
        out = Path(args.out).expanduser()
        out = out if out.is_absolute() else workspace / out
    elif args.filename:
        out = output_dir / args.filename
    else:
        prompt = args.prompt if args.prompt else (Path(args.prompt_file).stem if args.prompt_file else "image")
        ext = args.output_format or "png"
        out = output_dir / f"{slugify(prompt)}.{ext}"

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not args.force:
        out = unique_path(out)
    return out


def add_optional(cmd: list[str], flag: str, value: Any) -> None:
    if value is not None:
        cmd.extend([flag, str(value)])


def resolve_existing_path(path: str, workspace: Path) -> str:
    candidate = Path(path).expanduser()
    candidate = candidate if candidate.is_absolute() else workspace / candidate
    if not candidate.exists():
        fail(f"input image not found: {candidate}")
    return str(candidate)


def build_command(args: argparse.Namespace, python_path: Path, cli_path: Path, out: Path, workspace: Path) -> list[str]:
    if not cli_path.exists():
        fail(f"imagegen CLI not found: {cli_path}")
    if not args.prompt and not args.prompt_file:
        fail("provide --prompt or --prompt-file")
    if args.mode == "edit" and not args.image:
        fail("--mode edit requires at least one --image")
    if args.mode == "generate" and args.image:
        fail("--mode generate cannot be combined with --image")

    command = "edit" if args.image or args.mode == "edit" else "generate"

    cmd = [
        str(python_path),
        str(cli_path),
        command,
        "--model",
        args.model,
        "--size",
        args.size,
        "--quality",
        args.quality,
        "--out",
        str(out),
    ]
    if command == "edit":
        for image in args.image or []:
            cmd.extend(["--image", resolve_existing_path(image, workspace)])
        add_optional(cmd, "--mask", resolve_existing_path(args.mask, workspace) if args.mask else None)
    add_optional(cmd, "--prompt", args.prompt)
    add_optional(cmd, "--prompt-file", args.prompt_file)
    add_optional(cmd, "--n", args.n)
    add_optional(cmd, "--output-format", args.output_format)
    add_optional(cmd, "--output-compression", args.output_compression)
    add_optional(cmd, "--moderation", args.moderation)
    add_optional(cmd, "--use-case", args.use_case)
    add_optional(cmd, "--scene", args.scene)
    add_optional(cmd, "--subject", args.subject)
    add_optional(cmd, "--style", args.style)
    add_optional(cmd, "--composition", args.composition)
    add_optional(cmd, "--lighting", args.lighting)
    add_optional(cmd, "--palette", args.palette)
    add_optional(cmd, "--materials", args.materials)
    add_optional(cmd, "--text", args.text)
    add_optional(cmd, "--constraints", args.constraints)
    add_optional(cmd, "--negative", args.negative)
    add_optional(cmd, "--downscale-max-dim", args.downscale_max_dim)
    if args.no_augment:
        cmd.append("--no-augment")
    if args.dry_run:
        cmd.append("--dry-run")
    if args.force:
        cmd.append("--force")
    return cmd


def run_image_command(
    *,
    label: str,
    cmd: list[str],
    api_key: str,
    base_url: str,
    out: Path,
    args: argparse.Namespace,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = api_key
    env["OPENAI_BASE_URL"] = base_url

    print(f"Using {label} relay base URL: {base_url}")
    print(f"Writing output: {out}")
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)

    stdout = sanitize(result.stdout, api_key)
    stderr = sanitize(result.stderr, api_key)
    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)
    if result.returncode == 0 and args.dry_run:
        print(f"Dry-run output path: {out}")
    elif result.returncode == 0:
        print(f"Final output: {out}")
    return result


def api_call_was_attempted(result: subprocess.CompletedProcess[str]) -> bool:
    combined = f"{result.stdout}\n{result.stderr}"
    return (
        "Calling Image API" in combined
        or "Error code:" in combined
        or "openai." in combined
        or "AuthenticationError" in combined
        or "APIConnectionError" in combined
        or "APITimeoutError" in combined
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate or edit GPT Image 2 images through the configured relay.")
    parser.add_argument("--mode", choices=["auto", "generate", "edit"], default="auto")
    parser.add_argument("--prompt")
    parser.add_argument("--prompt-file")
    parser.add_argument("--image", action="append", help="Input image path. Repeat for multi-image edits.")
    parser.add_argument("--mask", help="Optional edit mask path for the first input image")
    parser.add_argument("--filename", help="Filename under the output directory")
    parser.add_argument("--out", help="Exact output path")
    parser.add_argument("--output-dir", help="Output directory; default: $PWD/outputs")
    parser.add_argument("--workspace", help="Workspace root; default: current directory")
    parser.add_argument("--auth-json", default=str(DEFAULT_AUTH_JSON))
    parser.add_argument("--image-auth-json", default=str(DEFAULT_IMAGE_AUTH_JSON))
    parser.add_argument("--profile", help="Named fallback relay profile. Reads ~/.codex/gpt-image-2-relay-<profile>.json or profiles.<profile> from --image-auth-json after the primary config fails.")
    parser.add_argument("--config-toml", default=str(DEFAULT_CONFIG_TOML))
    parser.add_argument("--provider", help="Model provider table name in config.toml; default: top-level model_provider")
    parser.add_argument("--python", help="Python executable to run the bundled imagegen CLI")
    parser.add_argument("--image-cli", default=str(default_cli_path()))
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument("--init-auth", action="store_true", help="Create a local fallback auth template and exit.")

    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--size", default="1024x1024")
    parser.add_argument("--quality", default="medium")
    parser.add_argument("--n", type=int, default=1)
    parser.add_argument("--output-format")
    parser.add_argument("--output-compression", type=int)
    parser.add_argument("--moderation")
    parser.add_argument("--use-case")
    parser.add_argument("--scene")
    parser.add_argument("--subject")
    parser.add_argument("--style")
    parser.add_argument("--composition")
    parser.add_argument("--lighting")
    parser.add_argument("--palette")
    parser.add_argument("--materials")
    parser.add_argument("--text")
    parser.add_argument("--constraints")
    parser.add_argument("--negative")
    parser.add_argument("--downscale-max-dim", type=int)
    parser.add_argument("--no-augment", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = Path(args.workspace).expanduser().resolve() if args.workspace else Path.cwd().resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    auth_path = Path(args.auth_json).expanduser()
    image_auth_path = Path(args.image_auth_json).expanduser()
    config_path = Path(args.config_toml).expanduser()

    if args.init_auth:
        template_path = profile_file(image_auth_path, args.profile) if args.profile else image_auth_path
        created = write_auth_template(template_path)
        action = "Created" if created else "Auth template already exists"
        print(f"{action}: {template_path}")
        print("Fill OPENAI_API_KEY and OPENAI_BASE_URL in that local file. Do not commit it.")
        return 0

    primary_config = read_json_object(auth_path, required=True)

    api_key = resolve_api_key(primary_config, allow_env=True, source=str(auth_path))
    base_url = os.environ.get("OPENAI_BASE_URL") or read_base_url(config_path, args.provider)

    python_path = ensure_runtime(workspace, args.python, args.skip_install)
    cli_path = Path(args.image_cli).expanduser()
    out = choose_output(args, workspace)
    cmd = build_command(args, python_path, cli_path, out, workspace)

    result = run_image_command(
        label="primary",
        cmd=cmd,
        api_key=api_key,
        base_url=base_url,
        out=out,
        args=args,
    )
    if (
        result.returncode != 0
        and not args.dry_run
        and api_call_was_attempted(result)
    ):
        fallback_config, fallback_source = resolve_relay_auth_config(
            image_auth_path,
            args.profile,
            create_missing=True,
        )
        fallback_api_key = resolve_api_key(
            fallback_config,
            allow_env=False,
            source=fallback_source or str(image_auth_path),
        )
        fallback_base_url = (
            base_url_from_config(fallback_config)
            or os.environ.get("OPENAI_BASE_URL")
            or read_base_url(config_path, args.provider)
        )
        if fallback_api_key == api_key and fallback_base_url == base_url:
            print(
                "Primary GPT Image 2 call failed; fallback relay config matches the primary config, so no retry was attempted.",
                file=sys.stderr,
            )
            return result.returncode
        print("Primary GPT Image 2 call failed; retrying with fallback relay config.", file=sys.stderr)
        result = run_image_command(
            label="fallback",
            cmd=cmd,
            api_key=fallback_api_key,
            base_url=fallback_base_url,
            out=out,
            args=args,
        )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
