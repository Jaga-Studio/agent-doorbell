"""setup.py / manage.py prompt: unattended run in a scratch copy (no services started). Python 3.11+."""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SetupTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        for sub in ("tools", "prompts"):
            shutil.copytree(os.path.join(ROOT, sub), os.path.join(self.d, sub))

    def tearDown(self):
        shutil.rmtree(self.d)

    def run_setup(self, *args):
        return subprocess.run([sys.executable, os.path.join(self.d, "tools", "setup.py"), *args],
                              capture_output=True, text=True, stdin=subprocess.DEVNULL)

    def test_unattended_setup_writes_config_tokens_and_prompts(self):
        r = self.run_setup("--members", "assistant:connector,commander:webhook,coder:ssh",
                           "--host", "bus.example.ts.net", "--no-start", "--lang", "en")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.d, "config.toml"), "rb") as f:
            cfg = tomllib.load(f)
        self.assertEqual(list(cfg["members"]), ["assistant", "commander", "coder"])
        self.assertEqual(cfg["bell"]["targets"]["commander"], {"type": "webhook", "secret_file": "secrets/bell/commander.env"})
        self.assertEqual(cfg["bell"]["targets"]["coder"]["type"], "ssh")
        self.assertNotIn("assistant", cfg["bell"]["targets"])
        self.assertIn("bus.example.ts.net", cfg["bus"]["allowed_hosts"])
        tokens = os.path.join(self.d, "secrets", "tokens.json")
        self.assertEqual(stat.S_IMODE(os.stat(tokens).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.d, "secrets")).st_mode), 0o700)
        with open(tokens) as f:
            self.assertEqual(sorted(json.load(f).values()), ["assistant", "coder", "commander"])
        self.assertIn("https://bus.example.ts.net/mcp", r.stdout)
        self.assertIn("agent-doorbell inbox", r.stdout)          # webhook prompt printed (no tty)
        self.assertIn("doorbell inbox", r.stdout)                # cli prompt
        self.assertNotIn("$", r.stdout.split("=== Next")[1].replace("$USER", ""))  # every placeholder filled

        # second run: config kept, no new tokens, nothing printed as a token
        r2 = self.run_setup("--no-start")
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn("Using the existing config.toml", r2.stdout)
        self.assertNotIn("shown once", r2.stdout)

    def test_prompt_command_respects_can_send_to_and_lang(self):
        with open(os.path.join(self.d, "config.toml"), "w") as f:
            f.write('[bus]\nallowed_hosts = ["h.ts.net", "127.0.0.1:8765"]\n'
                    '[members.a]\n[members.b]\n[members.c]\ncan_send_to = ["a"]\n')
        r = subprocess.run([sys.executable, os.path.join(self.d, "tools", "manage.py"), "prompt", "c", "--lang", "ja"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("「c」", r.stdout)
        self.assertIn("a と共有", r.stdout)
        self.assertIn("agent-doorbell（a と共有", r.stdout)  # b is not a peer of c
        self.assertIn("https://h.ts.net/mcp", r.stdout)


if __name__ == "__main__":
    unittest.main()
