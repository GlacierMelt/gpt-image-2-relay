import base64
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "gpt-image-2-relay" / "scripts" / "generate.py"
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2GQAAAABJRU5ErkJggg=="
)


class RelayHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.requests.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "content_type": self.headers.get("Content-Type"),
                "body": body,
            }
        )
        if self.server.response_mode == "url":
            response = {"data": [{"url": "/image.png"}]}
        else:
            response = {
                "data": [
                    {
                        "b64_json": base64.b64encode(PNG_BYTES).decode("ascii"),
                    }
                ]
            }
        encoded = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path != "/image.png":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(PNG_BYTES)))
        self.end_headers()
        self.wfile.write(PNG_BYTES)

    def log_message(self, *_args):
        return


class LocalRelay:
    def __init__(self, response_mode="b64"):
        self.response_mode = response_mode

    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RelayHandler)
        self.server.requests = []
        self.server.response_mode = self.response_mode
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}/api/v1"
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def run_cli(*args, cwd):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=20,
    )


class RelayDriverTests(unittest.TestCase):
    def test_direct_profile_passes_custom_model_unchanged(self):
        with tempfile.TemporaryDirectory() as temp_value, LocalRelay() as relay:
            temp = Path(temp_value)
            auth = temp / "relay.json"
            auth.write_text(
                json.dumps(
                    {
                        "OPENAI_API_KEY": "test-key",
                        "OPENAI_BASE_URL": relay.base_url,
                        "driver": "openai-images",
                        "model": "特惠image2",
                        "size": "3:2",
                        "quality": "high",
                        "response_format": "b64_json",
                        "output_format": "png",
                    },
                    ensure_ascii=False,
                )
            )

            result = run_cli(
                "--image-auth-json",
                str(auth),
                "--workspace",
                str(temp),
                "--prompt",
                "test prompt",
                "--no-augment",
                "--filename",
                "custom.png",
                cwd=temp,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((temp / "outputs" / "custom.png").read_bytes(), PNG_BYTES)
            self.assertEqual(len(relay.server.requests), 1)
            request = relay.server.requests[0]
            payload = json.loads(request["body"])
            self.assertEqual(request["path"], "/api/v1/images/generations")
            self.assertEqual(request["authorization"], "Bearer test-key")
            self.assertEqual(payload["model"], "特惠image2")
            self.assertEqual(payload["size"], "3:2")
            self.assertEqual(payload["prompt"], "test prompt")

    def test_direct_driver_downloads_url_response(self):
        with tempfile.TemporaryDirectory() as temp_value, LocalRelay("url") as relay:
            temp = Path(temp_value)
            auth = temp / "relay.json"
            auth.write_text(
                json.dumps(
                    {
                        "OPENAI_API_KEY": "test-key",
                        "OPENAI_BASE_URL": relay.base_url,
                        "driver": "openai-images",
                        "model": "任意图片模型-v2",
                        "size": "custom-wide",
                        "response_format": "url",
                    },
                    ensure_ascii=False,
                )
            )

            result = run_cli(
                "--image-auth-json",
                str(auth),
                "--workspace",
                str(temp),
                "--prompt",
                "test prompt",
                "--filename",
                "downloaded.png",
                cwd=temp,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((temp / "outputs" / "downloaded.png").read_bytes(), PNG_BYTES)
            payload = json.loads(relay.server.requests[0]["body"])
            self.assertEqual(payload["model"], "任意图片模型-v2")
            self.assertEqual(payload["size"], "custom-wide")

    def test_direct_edit_uses_multipart_and_exact_model(self):
        with tempfile.TemporaryDirectory() as temp_value, LocalRelay() as relay:
            temp = Path(temp_value)
            source = temp / "source.png"
            source.write_bytes(PNG_BYTES)
            auth = temp / "relay.json"
            auth.write_text(
                json.dumps(
                    {
                        "OPENAI_API_KEY": "test-key",
                        "OPENAI_BASE_URL": relay.base_url,
                        "driver": "openai-images",
                        "model": "模型/实验-v3",
                        "size": "relay-native",
                        "response_format": "b64_json",
                    },
                    ensure_ascii=False,
                )
            )

            result = run_cli(
                "--image-auth-json",
                str(auth),
                "--workspace",
                str(temp),
                "--image",
                str(source),
                "--prompt",
                "preserve the subject",
                "--filename",
                "edited.png",
                cwd=temp,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((temp / "outputs" / "edited.png").read_bytes(), PNG_BYTES)
            request = relay.server.requests[0]
            self.assertEqual(request["path"], "/api/v1/images/edits")
            self.assertTrue(request["content_type"].startswith("multipart/form-data; boundary="))
            self.assertIn("模型/实验-v3".encode("utf-8"), request["body"])
            self.assertIn(b'name="image"; filename="source.png"', request["body"])

    def test_explicit_imagegen_driver_is_kept(self):
        with tempfile.TemporaryDirectory() as temp_value:
            temp = Path(temp_value)
            auth = temp / "relay.json"
            auth.write_text(
                json.dumps(
                    {
                        "OPENAI_API_KEY": "test-key",
                        "OPENAI_BASE_URL": "http://127.0.0.1:9/v1",
                    }
                )
            )
            fake_cli = temp / "fake_imagegen.py"
            fake_cli.write_text(
                "import json, sys\n"
                "print(json.dumps(sys.argv[1:], ensure_ascii=False))\n"
            )

            result = run_cli(
                "--image-auth-json",
                str(auth),
                "--workspace",
                str(temp),
                "--driver",
                "imagegen",
                "--python",
                sys.executable,
                "--image-cli",
                str(fake_cli),
                "--prompt",
                "test prompt",
                "--dry-run",
                cwd=temp,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("relay driver: imagegen (model: gpt-image-2)", result.stdout)
            self.assertIn('"gpt-image-2"', result.stdout)

    def test_standard_model_defaults_to_single_attempt_direct_driver(self):
        with tempfile.TemporaryDirectory() as temp_value:
            temp = Path(temp_value)
            auth = temp / "relay.json"
            auth.write_text(
                json.dumps(
                    {
                        "OPENAI_API_KEY": "test-key",
                        "OPENAI_BASE_URL": "http://127.0.0.1:9/api/v1",
                    }
                )
            )

            result = run_cli(
                "--image-auth-json",
                str(auth),
                "--workspace",
                str(temp),
                "--prompt",
                "test prompt",
                "--dry-run",
                cwd=temp,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("relay driver: openai-images (model: gpt-image-2)", result.stdout)
            self.assertNotIn("relay driver: imagegen", result.stdout)

    def test_prefixed_custom_model_uses_direct_driver_in_auto_mode(self):
        with tempfile.TemporaryDirectory() as temp_value:
            temp = Path(temp_value)
            auth = temp / "relay.json"
            auth.write_text(
                json.dumps(
                    {
                        "OPENAI_API_KEY": "test-key",
                        "OPENAI_BASE_URL": "http://127.0.0.1:9/api/v1",
                        "model": "gpt-image-2-4K 高质量线路",
                        "size": "21:9",
                    },
                    ensure_ascii=False,
                )
            )

            result = run_cli(
                "--image-auth-json",
                str(auth),
                "--workspace",
                str(temp),
                "--prompt",
                "test prompt",
                "--dry-run",
                cwd=temp,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("relay driver: openai-images", result.stdout)
            self.assertIn('"model": "gpt-image-2-4K 高质量线路"', result.stdout)
            self.assertIn('"size": "21:9"', result.stdout)

if __name__ == "__main__":
    unittest.main()
