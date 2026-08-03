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
                "body": body,
            }
        )
        if self.server.barrier is not None:
            try:
                self.server.barrier.wait(timeout=2)
            except threading.BrokenBarrierError:
                self.send_error(503, "requests did not overlap")
                return
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

    def log_message(self, *_args):
        return


class LocalRelay:
    def __init__(self, barrier=None):
        self.barrier = barrier

    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RelayHandler)
        self.server.requests = []
        self.server.barrier = self.barrier
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
        timeout=10,
    )


def common_args(temp, auth, prompt="test prompt"):
    args = [
        "--image-auth-json",
        str(auth),
        "--workspace",
        str(temp),
        "--driver",
        "openai-images",
        "--model",
        "gpt-image-2",
        "--response-format",
        "b64_json",
    ]
    if prompt is not None:
        args.extend(("--prompt", prompt))
    args.append("--no-augment")
    return tuple(args)


def relay_prompts(relay):
    return [json.loads(request["body"].decode("utf-8"))["prompt"] for request in relay.server.requests]


def relay_counts(relay):
    return [json.loads(request["body"].decode("utf-8"))["n"] for request in relay.server.requests]


class MultiProfileTests(unittest.TestCase):
    def test_default_direct_config_ignores_profiles(self):
        with tempfile.TemporaryDirectory() as temp_value, LocalRelay() as relay:
            temp = Path(temp_value)
            auth = temp / "relay.json"
            auth.write_text(
                json.dumps(
                    {
                        "OPENAI_API_KEY": "default-key",
                        "OPENAI_BASE_URL": relay.base_url,
                        "profiles": {
                            "relay_1": {
                                "OPENAI_API_KEY": "unused-key",
                                "OPENAI_BASE_URL": "http://127.0.0.1:9/v1",
                            },
                            "relay_2": {
                                "OPENAI_API_KEY": "unused-key-2",
                                "OPENAI_BASE_URL": "http://127.0.0.1:9/v1",
                            },
                        },
                    }
                )
            )

            result = run_cli(
                *common_args(temp, auth),
                "--filename",
                "single.png",
                cwd=temp,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((temp / "outputs" / "single.png").read_bytes(), PNG_BYTES)
            self.assertEqual(len(relay.server.requests), 1)
            self.assertEqual(relay.server.requests[0]["authorization"], "Bearer default-key")
            self.assertNotIn("unused-key", result.stdout + result.stderr)

    def test_single_named_profile_comes_from_inline_profiles(self):
        with tempfile.TemporaryDirectory() as temp_value, LocalRelay() as relay:
            temp = Path(temp_value)
            auth = temp / "relay.json"
            auth.write_text(
                json.dumps(
                    {
                        "OPENAI_API_KEY": "default-key",
                        "OPENAI_BASE_URL": "http://127.0.0.1:9/v1",
                        "profiles": {
                            "relay_1": {
                                "OPENAI_API_KEY": "profile-key",
                                "OPENAI_BASE_URL": relay.base_url,
                            }
                        },
                    }
                )
            )

            result = run_cli(
                "--profile",
                "relay_1",
                *common_args(temp, auth),
                "--filename",
                "profile.png",
                cwd=temp,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((temp / "outputs" / "profile.png").read_bytes(), PNG_BYTES)
            self.assertEqual(relay.server.requests[0]["authorization"], "Bearer profile-key")
            self.assertNotIn("profile-key", result.stdout + result.stderr)

    def test_standard_model_uses_imagegen_from_default_json(self):
        with tempfile.TemporaryDirectory() as temp_value:
            temp = Path(temp_value)
            auth = temp / "relay.json"
            auth.write_text(
                json.dumps(
                    {
                        "OPENAI_API_KEY": "default-key",
                        "OPENAI_BASE_URL": "http://127.0.0.1:9/v1",
                    }
                )
            )
            fake_cli = temp / "fake_imagegen.py"
            fake_cli.write_text(
                "import json, sys\n"
                "print(json.dumps(sys.argv[1:]))\n"
            )

            result = run_cli(
                "--image-auth-json",
                str(auth),
                "--workspace",
                str(temp),
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
            self.assertNotIn("default-key", result.stdout + result.stderr)

    def test_three_prompt_files_map_one_to_one_and_overlap(self):
        barrier = threading.Barrier(3)
        with (
            tempfile.TemporaryDirectory() as temp_value,
            LocalRelay(barrier) as first,
            LocalRelay(barrier) as second,
            LocalRelay(barrier) as third,
        ):
            temp = Path(temp_value)
            prompt_files = []
            for index in range(1, 4):
                path = temp / f"prompt-{index}.txt"
                path.write_text(f"assigned prompt {index}")
                prompt_files.append(path)
            auth = temp / "relay.json"
            auth.write_text(
                json.dumps(
                    {
                        "OPENAI_API_KEY": "default-key",
                        "OPENAI_BASE_URL": "http://127.0.0.1:9/v1",
                        "profiles": {
                            "relay_1": {
                                "OPENAI_API_KEY": "first-key",
                                "OPENAI_BASE_URL": first.base_url,
                            },
                            "relay_2": {
                                "OPENAI_API_KEY": "second-key",
                                "OPENAI_BASE_URL": second.base_url,
                            },
                            "relay_3": {
                                "OPENAI_API_KEY": "third-key",
                                "OPENAI_BASE_URL": third.base_url,
                            },
                        },
                    }
                )
            )

            result = run_cli(
                "--profiles",
                "relay_1,relay_2,relay_3",
                *common_args(temp, auth, prompt=None),
                "--prompt-file",
                str(prompt_files[0]),
                "--prompt-file",
                str(prompt_files[1]),
                "--prompt-file",
                str(prompt_files[2]),
                "--filename",
                "multi.png",
                cwd=temp,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((temp / "outputs" / "multi--p001--relay-1.png").read_bytes(), PNG_BYTES)
            self.assertEqual((temp / "outputs" / "multi--p002--relay-2.png").read_bytes(), PNG_BYTES)
            self.assertEqual((temp / "outputs" / "multi--p003--relay-3.png").read_bytes(), PNG_BYTES)
            self.assertEqual(first.server.requests[0]["authorization"], "Bearer first-key")
            self.assertEqual(second.server.requests[0]["authorization"], "Bearer second-key")
            self.assertEqual(third.server.requests[0]["authorization"], "Bearer third-key")
            self.assertEqual(relay_prompts(first), ["assigned prompt 1"])
            self.assertEqual(relay_prompts(second), ["assigned prompt 2"])
            self.assertEqual(relay_prompts(third), ["assigned prompt 3"])
            self.assertEqual(relay_counts(first), [1])
            self.assertEqual(relay_counts(second), [1])
            self.assertEqual(relay_counts(third), [1])
            self.assertIn("p001->relay_1, p002->relay_2, p003->relay_3", result.stdout)
            self.assertIn("Concurrent prompt summary", result.stdout)
            self.assertNotIn("first-key", result.stdout + result.stderr)
            self.assertNotIn("second-key", result.stdout + result.stderr)
            self.assertNotIn("third-key", result.stdout + result.stderr)

    def test_more_prompts_than_profiles_are_round_robin_without_duplicates(self):
        with (
            tempfile.TemporaryDirectory() as temp_value,
            LocalRelay() as first,
            LocalRelay() as second,
        ):
            temp = Path(temp_value)
            auth = temp / "relay.json"
            auth.write_text(
                json.dumps(
                    {
                        "profiles": {
                            "relay_1": {
                                "OPENAI_API_KEY": "first-key",
                                "OPENAI_BASE_URL": first.base_url,
                            },
                            "relay_2": {
                                "OPENAI_API_KEY": "second-key",
                                "OPENAI_BASE_URL": second.base_url,
                            },
                        }
                    }
                )
            )
            prompts = [f"round robin prompt {index}" for index in range(1, 6)]
            prompt_args = [item for prompt in prompts for item in ("--prompt", prompt)]

            result = run_cli(
                "--profiles",
                "relay_1,relay_2",
                *common_args(temp, auth, prompt=None),
                *prompt_args,
                "--filename",
                "batch.png",
                cwd=temp,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(relay_prompts(first), prompts[0::2])
            self.assertEqual(relay_prompts(second), prompts[1::2])
            self.assertEqual(relay_counts(first), [1, 1, 1])
            self.assertEqual(relay_counts(second), [1, 1])
            for index, profile in enumerate(("relay-1", "relay-2", "relay-1", "relay-2", "relay-1"), 1):
                self.assertEqual(
                    (temp / "outputs" / f"batch--p{index:03d}--{profile}.png").read_bytes(),
                    PNG_BYTES,
                )
            self.assertIn("Starting 5 prompt task(s) across 2 relay profile(s)", result.stdout)
            self.assertNotIn("first-key", result.stdout + result.stderr)
            self.assertNotIn("second-key", result.stdout + result.stderr)

    def test_profile_count_selects_only_requested_number(self):
        with tempfile.TemporaryDirectory() as temp_value:
            temp = Path(temp_value)
            auth = temp / "relay.json"
            auth.write_text(
                json.dumps(
                    {
                        "OPENAI_API_KEY": "default-key",
                        "OPENAI_BASE_URL": "http://127.0.0.1:9/v1",
                        "profiles": {
                            f"relay_{index}": {
                                "OPENAI_API_KEY": f"key-{index}",
                                "OPENAI_BASE_URL": f"http://127.0.0.1:{9000 + index}/v1",
                            }
                            for index in range(1, 4)
                        },
                    }
                )
            )

            result = run_cli(
                "--profile-count",
                "2",
                *common_args(temp, auth, prompt=None),
                "--prompt",
                "first count prompt",
                "--prompt",
                "second count prompt",
                "--filename",
                "count.png",
                "--dry-run",
                cwd=temp,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("count--p001--relay-1.png", result.stdout)
            self.assertIn("count--p002--relay-2.png", result.stdout)
            self.assertNotIn("relay-3.png", result.stdout)

    def test_fewer_prompts_than_profiles_leave_extra_profile_unused(self):
        with tempfile.TemporaryDirectory() as temp_value:
            temp = Path(temp_value)
            auth = temp / "relay.json"
            auth.write_text(
                json.dumps(
                    {
                        "profiles": {
                            f"relay_{index}": {
                                "OPENAI_API_KEY": f"key-{index}",
                                "OPENAI_BASE_URL": f"http://127.0.0.1:{9100 + index}/v1",
                            }
                            for index in range(1, 4)
                        }
                    }
                )
            )

            result = run_cli(
                "--profiles",
                "all",
                *common_args(temp, auth, prompt=None),
                "--prompt",
                "first prompt",
                "--prompt",
                "second prompt",
                "--filename",
                "short.png",
                "--dry-run",
                cwd=temp,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("short--p001--relay-1.png", result.stdout)
            self.assertIn("short--p002--relay-2.png", result.stdout)
            self.assertIn("Selected profiles without an assigned prompt: relay_3", result.stdout)
            self.assertNotIn("short--p003", result.stdout)
            self.assertNotIn("key-1", result.stdout + result.stderr)
            self.assertNotIn("key-2", result.stdout + result.stderr)
            self.assertNotIn("key-3", result.stdout + result.stderr)

    def test_multi_mode_requires_two_profiles(self):
        with tempfile.TemporaryDirectory() as temp_value:
            temp = Path(temp_value)
            auth = temp / "relay.json"
            auth.write_text(
                json.dumps(
                    {
                        "profiles": {
                            "relay_1": {
                                "OPENAI_API_KEY": "test-key",
                                "OPENAI_BASE_URL": "http://127.0.0.1:9001/v1",
                            }
                        }
                    }
                )
            )

            result = run_cli(
                "--profiles",
                "relay_1",
                *common_args(temp, auth),
                "--dry-run",
                cwd=temp,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires at least two", result.stderr)


if __name__ == "__main__":
    unittest.main()
