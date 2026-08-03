#!/usr/bin/env python3
"""Generate or edit images through configurable relay drivers.

This wrapper intentionally keeps API keys out of command-line arguments and
redacts key-like strings from process output.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


DEFAULT_AUTH_JSON = Path.home() / ".codex" / "auth.json"
DEFAULT_IMAGE_AUTH_JSON = Path.home() / ".codex" / "gpt-image-2-relay-auth.json"
DEFAULT_CONFIG_TOML = Path.home() / ".codex" / "config.toml"
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_DRIVER = "auto"
DEFAULT_SIZE = "1024x1024"
DEFAULT_QUALITY = "medium"
DEFAULT_RESPONSE_FORMAT = "url"
DEFAULT_REQUEST_TIMEOUT = 600.0
KNOWN_IMAGEGEN_MODELS = {
    "gpt-image-2",
    "gpt-image-1.5",
    "gpt-image-1",
    "gpt-image-1-mini",
}
KEY_RE = re.compile(r"sk-[A-Za-z0-9_-]{8,}")
BASE_URL_KEYS = ("OPENAI_BASE_URL", "base_url", "BASE_URL", "url")
PROVIDER_API_KEY_KEYS = ("experimental_bearer_token", "OPENAI_API_KEY", "api_key", "bearer_token")
IMAGE_RESPONSE_KEYS = {"url", "b64_json", "b64Json"}
DRIVER_ALIASES = {
    "auto": "auto",
    "imagegen": "imagegen",
    "system": "imagegen",
    "openai-images": "openai-images",
    "openai": "openai-images",
    "direct": "openai-images",
    "relay": "openai-images",
}
PROVIDER_IMAGE_OPTIONS = {
    "driver": "image_driver",
    "model": "image_model",
    "size": "image_size",
    "quality": "image_quality",
    "response_format": "image_response_format",
    "output_format": "image_output_format",
    "style": "image_style",
    "background": "image_background",
    "upscale": "image_upscale",
    "request_timeout": "image_request_timeout",
    "extra_json": "image_extra_json",
}
AUTH_TEMPLATE_INSTRUCTIONS = (
    "Fill OPENAI_API_KEY and OPENAI_BASE_URL. Optionally set driver, model, size, "
    "quality, response_format, and output_format for this relay. Leave "
    "OPENAI_BASE_URL empty to reuse ~/.codex/config.toml. Keep this file in "
    "~/.codex and do not commit it."
)


@dataclass
class DriverResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    attempted: bool = False


class RelayRequestError(RuntimeError):
    """Readable HTTP, response, or download error from a direct relay."""


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
        "driver": "auto",
        "model": "",
        "size": "",
        "quality": "",
        "response_format": "",
        "output_format": "",
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


def api_key_from_provider_table(table: dict[str, Any]) -> str | None:
    for key in PROVIDER_API_KEY_KEYS:
        value = table.get(key)
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


def read_provider_table(path: Path, provider: str | None) -> tuple[str, dict[str, Any]]:
    try:
        data = _load_toml(path)
    except FileNotFoundError:
        fail(f"config file not found: {path}")

    selected = provider or data.get("model_provider") or "custom"
    providers = data.get("model_providers")
    if isinstance(providers, dict):
        table = providers.get(str(selected))
        if isinstance(table, dict):
            return str(selected), table

    fail(f"model provider {selected!r} missing in {path}")


def read_base_url(path: Path, provider: str | None) -> str:
    selected, table = read_provider_table(path, provider)
    value = table.get("base_url")
    if isinstance(value, str) and value.strip():
        return value.strip()

    fail(f"base_url missing for model provider {selected!r} in {path}")


def normalize_openai_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        fail("base_url is empty")
    if value.endswith("/v1"):
        return value
    return f"{value}/v1"


def safe_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        host = parsed.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        try:
            port_value = parsed.port
        except ValueError:
            port_value = None
        port = f":{port_value}" if port_value else ""
        return f"{parsed.scheme}://{host}{port}{parsed.path}".rstrip("/")
    return value.split("?", 1)[0].split("#", 1)[0]


def validate_http_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RelayRequestError(f"invalid relay base URL: {safe_base_url(value)!r}")
    return value


def provider_image_config(table: dict[str, Any]) -> dict[str, Any]:
    return {
        option: table[field]
        for option, field in PROVIDER_IMAGE_OPTIONS.items()
        if field in table
    }


def nonempty_config_value(config: dict[str, Any], key: str) -> Any:
    value = config.get(key)
    if isinstance(value, str) and not value.strip():
        return None
    return value


def parse_extra_json(value: Any, source: str) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            fail(f"{source} must contain a JSON object: {exc}")
        if isinstance(parsed, dict):
            return parsed
    fail(f"{source} must be a JSON object")
    return {}


def resolve_driver(value: Any, model: str) -> str:
    requested = str(value or DEFAULT_DRIVER).strip().lower()
    driver = DRIVER_ALIASES.get(requested)
    if not driver:
        choices = ", ".join(sorted(DRIVER_ALIASES))
        fail(f"unknown relay driver {requested!r}; choose one of: {choices}")
    if driver == "auto":
        return "imagegen" if model in KNOWN_IMAGEGEN_MODELS else "openai-images"
    return driver


def resolve_attempt_args(args: argparse.Namespace, config: dict[str, Any]) -> argparse.Namespace:
    resolved = argparse.Namespace(**vars(args))

    def choose(name: str, default: Any = None) -> Any:
        cli_value = getattr(args, name, None)
        if cli_value is not None:
            return cli_value
        config_value = nonempty_config_value(config, name)
        return default if config_value is None else config_value

    resolved.model = str(choose("model", DEFAULT_MODEL)).strip()
    if not resolved.model:
        fail("model must not be empty")
    resolved.driver = resolve_driver(choose("driver", DEFAULT_DRIVER), resolved.model)
    resolved.size = str(choose("size", DEFAULT_SIZE)).strip()
    resolved.quality = str(choose("quality", DEFAULT_QUALITY)).strip()
    resolved.response_format = str(choose("response_format", DEFAULT_RESPONSE_FORMAT)).strip()
    if resolved.response_format not in {"url", "b64_json"}:
        fail("response-format must be url or b64_json")
    resolved.output_format = choose("output_format")
    resolved.style = choose("style")
    resolved.background = choose("background")
    resolved.upscale = choose("upscale")
    try:
        resolved.request_timeout = float(choose("request_timeout", DEFAULT_REQUEST_TIMEOUT))
    except (TypeError, ValueError):
        fail("request-timeout must be a number")
    if resolved.request_timeout <= 0:
        fail("request-timeout must be greater than zero")
    extra_value = args.extra_json if args.extra_json is not None else nonempty_config_value(config, "extra_json")
    resolved.extra_json = parse_extra_json(extra_value, "extra-json")
    return resolved


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


def read_prompt_text(args: argparse.Namespace, workspace: Path) -> str:
    if args.prompt is not None:
        prompt = args.prompt
    elif args.prompt_file:
        prompt_path = Path(args.prompt_file).expanduser()
        prompt_path = prompt_path if prompt_path.is_absolute() else workspace / prompt_path
        try:
            prompt = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            fail(f"prompt file not found: {prompt_path}")
    else:
        fail("provide --prompt or --prompt-file")
    prompt = prompt.strip()
    if not prompt:
        fail("prompt must not be empty")
    return prompt


def augment_prompt(args: argparse.Namespace, prompt: str) -> str:
    if args.no_augment:
        return prompt
    fields = (
        ("Use case", args.use_case),
        ("Primary request", prompt),
        ("Scene/background", args.scene),
        ("Subject", args.subject),
        ("Style/medium", args.style),
        ("Composition/framing", args.composition),
        ("Lighting/mood", args.lighting),
        ("Color palette", args.palette),
        ("Materials/textures", args.materials),
        ("Text (verbatim)", f'"{args.text}"' if args.text else None),
        ("Constraints", args.constraints),
        ("Avoid", args.negative),
    )
    return "\n".join(f"{label}: {value}" for label, value in fields if value)


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def embedded_error(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if error:
        if isinstance(error, dict):
            return str(error.get("message") or compact_json(error))
        return str(error)
    code = payload.get("code")
    if code not in (None, 0, "0", 200, "200") and payload.get("data") is None:
        return str(payload.get("msg") or payload.get("message") or compact_json(payload))
    return None


def decode_json_body(raw: bytes, content_type: str | None = None) -> Any:
    if not raw:
        return {}
    charset = "utf-8"
    if content_type and "charset=" in content_type:
        charset = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
    text = raw.decode(charset, errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RelayRequestError(f"expected JSON response, received: {text[:1000]}") from exc


def request_relay_json(
    *,
    method: str,
    url: str,
    api_key: str,
    timeout: float,
    payload: dict[str, Any] | None = None,
    body: bytes | None = None,
    content_type: str | None = None,
) -> Any:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "gpt-image-2-relay-skill/2.0",
    }
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        content_type = "application/json"
    if content_type:
        headers["Content-Type"] = content_type
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            result = decode_json_body(response.read(), response.headers.get("Content-Type"))
    except HTTPError as exc:
        raw = exc.read()
        try:
            detail = decode_json_body(raw, exc.headers.get("Content-Type"))
            message = embedded_error(detail) or compact_json(detail)
        except RelayRequestError:
            message = raw.decode("utf-8", errors="replace")[:2000]
        raise RelayRequestError(f"HTTP {exc.code} from {safe_base_url(url)}: {message}") from exc
    except URLError as exc:
        raise RelayRequestError(f"request failed for {safe_base_url(url)}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RelayRequestError(f"request timed out for {safe_base_url(url)}") from exc

    message = embedded_error(result)
    if message:
        raise RelayRequestError(f"API error from {safe_base_url(url)}: {message}")
    return result


def validate_reference_images(paths: Iterable[str], workspace: Path) -> list[Path]:
    images = [Path(resolve_existing_path(path, workspace)) for path in paths]
    if len(images) > 8:
        fail("the direct relay driver accepts at most 8 reference images")
    total = sum(path.stat().st_size for path in images)
    if total > 40 * 1024 * 1024:
        fail("reference images exceed the direct relay driver's 40 MB total limit")
    return images


def multipart_body(fields: dict[str, Any], files: list[tuple[str, Path]]) -> tuple[bytes, str]:
    boundary = f"----gpt-image-relay-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    def add_line(value: str = "") -> None:
        chunks.append(value.encode("utf-8") + b"\r\n")

    for name, value in fields.items():
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            value = compact_json(value)
        add_line(f"--{boundary}")
        add_line(f'Content-Disposition: form-data; name="{name}"')
        add_line()
        add_line(str(value))

    for field_name, path in files:
        filename = path.name.replace('"', "_")
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        add_line(f"--{boundary}")
        add_line(f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"')
        add_line(f"Content-Type: {mime_type}")
        add_line()
        chunks.append(path.read_bytes())
        chunks.append(b"\r\n")

    add_line(f"--{boundary}--")
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def parse_json_string(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def find_image_items(value: Any) -> list[dict[str, Any]] | None:
    value = parse_json_string(value)
    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            if any(IMAGE_RESPONSE_KEYS.intersection(item) for item in value):
                return value
        for item in value:
            found = find_image_items(item)
            if found:
                return found
        return None
    if not isinstance(value, dict):
        return None
    for key in ("data", "images"):
        items = value.get(key)
        if isinstance(items, list) and items and all(isinstance(item, dict) for item in items):
            if any(IMAGE_RESPONSE_KEYS.intersection(item) for item in items):
                return items
    for key in ("response", "responseBody", "response_body", "result", "output", "data", "job"):
        if key in value:
            found = find_image_items(value[key])
            if found:
                return found
    return None


def output_paths(out: Path, count: int, force: bool) -> list[Path]:
    if count == 1:
        candidates = [out]
    else:
        candidates = [out.with_name(f"{out.stem}-{index}{out.suffix}") for index in range(1, count + 1)]
    return [path if force or not path.exists() else unique_path(path) for path in candidates]


def download_relay_image(url: str, destination: Path, api_key: str, base_url: str, timeout: float) -> None:
    base = validate_http_base_url(base_url)
    origin = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
    absolute_url = urljoin(f"{origin}/", url)
    parsed = urlparse(absolute_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RelayRequestError(f"invalid image URL in relay response: {safe_base_url(absolute_url)!r}")
    headers = {"User-Agent": "gpt-image-2-relay-skill/2.0"}

    def fetch(current_headers: dict[str, str]) -> bytes:
        request = Request(absolute_url, headers=current_headers, method="GET")
        with urlopen(request, timeout=timeout) as response:
            return response.read()

    try:
        data = fetch(headers)
    except HTTPError as exc:
        same_origin = f"{parsed.scheme}://{parsed.netloc}" == origin
        if exc.code not in {401, 403} or not same_origin:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RelayRequestError(f"image download failed with HTTP {exc.code}: {detail}") from exc
        headers["Authorization"] = f"Bearer {api_key}"
        try:
            data = fetch(headers)
        except (HTTPError, URLError) as retry_exc:
            raise RelayRequestError(f"authenticated image download failed: {retry_exc}") from retry_exc
    except URLError as exc:
        raise RelayRequestError(f"image download failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RelayRequestError("image download timed out") from exc
    destination.write_bytes(data)


def save_relay_images(
    response: Any,
    out: Path,
    api_key: str,
    base_url: str,
    timeout: float,
    force: bool,
) -> list[Path]:
    items = find_image_items(response)
    if not items:
        raise RelayRequestError("relay response did not contain url or b64_json image data")
    destinations = output_paths(out, len(items), force)
    saved: list[Path] = []
    for item, destination in zip(items, destinations):
        destination.parent.mkdir(parents=True, exist_ok=True)
        encoded = item.get("b64_json") or item.get("b64Json")
        if encoded:
            encoded = str(encoded)
            if encoded.startswith("data:") and "," in encoded:
                encoded = encoded.split(",", 1)[1]
            try:
                data = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise RelayRequestError("relay returned invalid Base64 image data") from exc
            destination.write_bytes(data)
        elif item.get("url"):
            download_relay_image(str(item["url"]), destination, api_key, base_url, timeout)
        else:
            continue
        saved.append(destination)
    if not saved:
        raise RelayRequestError("relay response did not contain usable image data")
    return saved


def direct_relay_payload(args: argparse.Namespace, prompt: str) -> dict[str, Any]:
    payload = dict(args.extra_json)
    payload.update(
        {
            "model": args.model,
            "prompt": prompt,
            "n": args.n,
            "size": args.size,
            "quality": args.quality,
            "response_format": args.response_format,
        }
    )
    for key in ("style", "background", "output_format", "upscale", "output_compression", "moderation"):
        value = getattr(args, key, None)
        if value is not None:
            payload[key] = value
    return payload


def run_openai_images_driver(
    *,
    label: str,
    args: argparse.Namespace,
    api_key: str,
    base_url: str,
    out: Path,
    workspace: Path,
) -> DriverResult:
    command = "edit" if args.image or args.mode == "edit" else "generate"
    if args.mode == "edit" and not args.image:
        return DriverResult(2, stderr="--mode edit requires at least one --image\n")
    if args.mode == "generate" and args.image:
        return DriverResult(2, stderr="--mode generate cannot be combined with --image\n")
    if args.downscale_max_dim is not None:
        return DriverResult(2, stderr="--downscale-max-dim is not supported by the openai-images driver\n")

    try:
        relay_base_url = validate_http_base_url(base_url)
    except RelayRequestError as exc:
        return DriverResult(2, stderr=f"{exc}\n")
    prompt = augment_prompt(args, read_prompt_text(args, workspace))
    payload = direct_relay_payload(args, prompt)
    endpoint = f"{relay_base_url}/images/{'edits' if command == 'edit' else 'generations'}"

    print(f"Using {label} relay base URL: {safe_base_url(relay_base_url)}")
    print(f"Using {label} relay driver: openai-images (model: {args.model})")
    print(f"Writing output: {out}")
    if args.dry_run:
        preview = {
            "driver": "openai-images",
            "endpoint": safe_base_url(endpoint),
            "output": str(out),
            **payload,
        }
        if command == "edit":
            preview["images"] = [resolve_existing_path(path, workspace) for path in args.image or []]
            if args.mask:
                preview["mask"] = resolve_existing_path(args.mask, workspace)
        print(json.dumps(preview, ensure_ascii=False, indent=2, sort_keys=True))
        print(f"Dry-run output path: {out}")
        return DriverResult(0)

    try:
        if command == "generate":
            response = request_relay_json(
                method="POST",
                url=endpoint,
                api_key=api_key,
                timeout=args.request_timeout,
                payload=payload,
            )
        else:
            images = validate_reference_images(args.image or [], workspace)
            image_field = "image" if len(images) == 1 else "image[]"
            files = [(image_field, path) for path in images]
            if args.mask:
                files.append(("mask", Path(resolve_existing_path(args.mask, workspace))))
            body, content_type = multipart_body(payload, files)
            response = request_relay_json(
                method="POST",
                url=endpoint,
                api_key=api_key,
                timeout=args.request_timeout,
                body=body,
                content_type=content_type,
            )
        saved = save_relay_images(
            response,
            out,
            api_key,
            relay_base_url,
            args.request_timeout,
            args.force,
        )
    except RelayRequestError as exc:
        message = sanitize(str(exc), api_key)
        return DriverResult(1, stderr=f"Direct relay request failed: {message}\n", attempted=True)

    for path in saved:
        print(f"Final output: {path}")
    return DriverResult(0, stdout="\n".join(str(path) for path in saved), attempted=True)


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
    add_optional(cmd, "--background", args.background)
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
) -> DriverResult:
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = api_key
    env["OPENAI_BASE_URL"] = base_url

    print(f"Using {label} relay base URL: {safe_base_url(base_url)}")
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
    return DriverResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        attempted=api_call_was_attempted_output(result.stdout, result.stderr),
    )


def api_call_was_attempted_output(stdout: str, stderr: str) -> bool:
    combined = f"{stdout}\n{stderr}"
    return (
        "Calling Image API" in combined
        or "Error code:" in combined
        or "openai." in combined
        or "AuthenticationError" in combined
        or "APIConnectionError" in combined
        or "APITimeoutError" in combined
    )


def api_call_was_attempted(result: DriverResult) -> bool:
    return result.attempted or api_call_was_attempted_output(result.stdout, result.stderr)


def run_relay_attempt(
    *,
    label: str,
    args: argparse.Namespace,
    api_key: str,
    base_url: str,
    out: Path,
    workspace: Path,
) -> DriverResult:
    if args.driver == "openai-images":
        result = run_openai_images_driver(
            label=label,
            args=args,
            api_key=api_key,
            base_url=base_url,
            out=out,
            workspace=workspace,
        )
    elif args.driver == "imagegen":
        python_path = ensure_runtime(workspace, args.python, args.skip_install)
        cli_path = Path(args.image_cli).expanduser()
        cmd = build_command(args, python_path, cli_path, out, workspace)
        print(f"Using {label} relay driver: imagegen (model: {args.model})")
        result = run_image_command(
            label=label,
            cmd=cmd,
            api_key=api_key,
            base_url=base_url,
            out=out,
            args=args,
        )
    else:
        result = DriverResult(2, stderr=f"unsupported relay driver: {args.driver}\n")

    if result.stderr and result.returncode != 0 and args.driver == "openai-images":
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)
    return result


def attempt_signature(
    api_key: str,
    base_url: str,
    args: argparse.Namespace,
) -> tuple[Any, ...]:
    return (
        api_key,
        base_url.rstrip("/"),
        args.driver,
        args.model,
        args.size,
        args.quality,
        args.response_format,
        args.output_format,
        args.style,
        args.background,
        args.upscale,
        compact_json(args.extra_json),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate or edit images through configurable relay drivers.")
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
    parser.add_argument("--profile", help="Named relay profile. By default it is used after the primary relay fails.")
    parser.add_argument(
        "--use-profile",
        action="store_true",
        help="Use --profile, or the default image auth JSON, directly instead of trying the primary provider first.",
    )
    parser.add_argument("--config-toml", default=str(DEFAULT_CONFIG_TOML))
    parser.add_argument("--provider", help="Model provider table name in config.toml; default: top-level model_provider")
    parser.add_argument("--python", help="Python executable to run the bundled imagegen CLI")
    parser.add_argument("--image-cli", default=str(default_cli_path()))
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument("--init-auth", action="store_true", help="Create a local relay auth template and exit.")

    parser.add_argument(
        "--driver",
        help="Relay driver: auto, imagegen, or openai-images. Config may also set driver.",
    )
    parser.add_argument("--model", help=f"Image model; default: config value or {DEFAULT_MODEL}")
    parser.add_argument("--size", help=f"Pixel size or relay-specific ratio; default: {DEFAULT_SIZE}")
    parser.add_argument("--quality", help=f"Image quality; default: {DEFAULT_QUALITY}")
    parser.add_argument("--n", type=int, default=1)
    parser.add_argument("--output-format")
    parser.add_argument("--output-compression", type=int)
    parser.add_argument("--moderation")
    parser.add_argument("--response-format", choices=("url", "b64_json"))
    parser.add_argument("--background")
    parser.add_argument("--upscale")
    parser.add_argument("--request-timeout", type=float)
    parser.add_argument("--extra-json", help="Additional JSON object for the openai-images request payload.")
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

    if args.n < 1 or args.n > 10:
        fail("n must be between 1 and 10")

    if args.use_profile:
        selected_config, selected_source = resolve_relay_auth_config(
            image_auth_path,
            args.profile,
            create_missing=True,
        )
        selected_api_key = resolve_api_key(
            selected_config,
            allow_env=False,
            source=selected_source or str(image_auth_path),
        )
        selected_base_url = base_url_from_config(selected_config)
        if not selected_base_url:
            selected_base_url = normalize_openai_base_url(read_base_url(config_path, args.provider))
        selected_args = resolve_attempt_args(args, selected_config)
        out = choose_output(selected_args, workspace)
        label = f"profile {args.profile!r}" if args.profile else "configured"
        result = run_relay_attempt(
            label=label,
            args=selected_args,
            api_key=selected_api_key,
            base_url=selected_base_url,
            out=out,
            workspace=workspace,
        )
        return result.returncode

    provider_name, provider_table = read_provider_table(config_path, args.provider)
    primary_base_url = normalize_openai_base_url(read_base_url(config_path, args.provider))
    primary_config = read_json_object(auth_path)
    api_key = api_key_from_provider_table(provider_table) or resolve_api_key(
        primary_config,
        allow_env=False,
        source=f"{config_path} model_providers.{provider_name} or {auth_path}",
    )
    primary_args = resolve_attempt_args(args, provider_image_config(provider_table))
    out = choose_output(primary_args, workspace)
    result = run_relay_attempt(
        label="primary",
        args=primary_args,
        api_key=api_key,
        base_url=primary_base_url,
        out=out,
        workspace=workspace,
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
        fallback_base_url = base_url_from_config(fallback_config) or primary_base_url
        fallback_args = resolve_attempt_args(args, fallback_config)
        if attempt_signature(fallback_api_key, fallback_base_url, fallback_args) == attempt_signature(
            api_key,
            primary_base_url,
            primary_args,
        ):
            print(
                "Primary image call failed; fallback relay config matches the primary request, so no retry was attempted.",
                file=sys.stderr,
            )
            return result.returncode
        print("Primary image call failed; retrying with fallback relay config.", file=sys.stderr)
        result = run_relay_attempt(
            label="fallback",
            args=fallback_args,
            api_key=fallback_api_key,
            base_url=fallback_base_url,
            out=out,
            workspace=workspace,
        )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
