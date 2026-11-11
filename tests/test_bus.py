"""Bus + CLI + manage.py end-to-end. Needs bus/requirements.txt installed (skipped otherwise)."""

import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAS_DEPS = all(importlib.util.find_spec(m) for m in ("mcp", "uvicorn"))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipUnless(HAS_DEPS, "bus dependencies not installed")
class BusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        cls.port = free_port()
        cls.url = f"http://127.0.0.1:{cls.port}/mcp"
        with open(os.path.join(cls.d, "config.toml"), "w") as f:
            f.write(f"""
[bus]
allowed_hosts = ["127.0.0.1:{cls.port}"]
max_body_chars = 100
[members.alice]
[members.bob]
[members.helper]
can_send_to = ["alice"]
""")
        cls.tokens = os.path.join(cls.d, "secrets", "tokens.json")
        cls.tok = {}
        for name in ("alice", "bob", "helper"):
            r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "manage.py"), "member", "add", name,
                                "--tokens", cls.tokens], capture_output=True, text=True, check=True)
            cls.tok[name] = r.stdout.strip()
            path = os.path.join(cls.d, f"{name}.token")
            with open(path, "w") as f:
                f.write(cls.tok[name])
        env = dict(os.environ, DOORBELL_CONFIG=os.path.join(cls.d, "config.toml"), BUS_DB=os.path.join(cls.d, "bus.db"),
                   BUS_TOKENS=cls.tokens, BUS_BIND_HOST="127.0.0.1", BUS_PORT=str(cls.port))
        cls.p = subprocess.Popen([sys.executable, os.path.join(ROOT, "bus", "server.py")], env=env,
                                 stderr=subprocess.PIPE, text=True)
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", cls.port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        cls.p.terminate()
        log = cls.p.communicate(timeout=10)[1]
        for t in cls.tok.values():
            assert t not in log, "token leaked into the server log"

    def cli(self, who, *args, stdin=""):
        env = dict(os.environ, DOORBELL_URL=self.url, DOORBELL_TOKEN_FILE=os.path.join(self.d, f"{who}.token"))
        r = subprocess.run([sys.executable, os.path.join(ROOT, "cli", "doorbell"), *args], input=stdin,
                           capture_output=True, text=True, env=env)
        self.assertNotIn(self.tok[who], r.stdout + r.stderr)
        return r

    def ok(self, who, *args, stdin=""):
        r = self.cli(who, *args, stdin=stdin)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_token_file_has_hashes_only(self):
        raw = open(self.tokens).read()
        for t in self.tok.values():
            self.assertNotIn(t, raw)
        self.assertEqual(oct(os.stat(self.tokens).st_mode & 0o777), "0o600")

    def test_no_token_is_401(self):
        req = urllib.request.Request(self.url, data=b"{}", method="POST", headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(e.exception.code, 401)

    def test_send_inbox_reply_ack(self):
        sent = self.ok("alice", "send", "bob", stdin="please check X")
        inbox = self.ok("bob", "inbox")
        self.assertIn(sent["id"], [m["id"] for m in inbox["messages"]])
        self.assertNotIn(sent["id"], [m["id"] for m in self.ok("alice", "inbox")["messages"]])
        rep = self.ok("bob", "reply", str(sent["id"]), stdin="done")
        self.assertEqual(rep["to"], "alice")
        got = [m for m in self.ok("alice", "inbox")["messages"] if m["id"] == rep["id"]][0]
        self.assertEqual(got["reply_to"], sent["id"])
        self.assertEqual(self.ok("alice", "ack", str(sent["id"]))["acked"], [])  # not alice's message
        self.assertEqual(self.ok("bob", "ack", str(sent["id"]))["acked"], [sent["id"]])
        self.assertEqual(self.ok("bob", "ack", str(sent["id"]))["acked"], [])

    def test_can_send_to_is_enforced(self):
        self.ok("helper", "send", "alice", stdin="hi")
        r = self.cli("helper", "send", "bob", stdin="hi")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("may only send to", r.stderr)

    def test_limits(self):
        r = self.cli("alice", "send", "bob", stdin="x" * 101)
        self.assertIn("exceeds", r.stderr)
        r = self.cli("alice", "send", "alice", stdin="x")
        self.assertIn("yourself", r.stderr)
        r = self.cli("alice", "send", "nobody", stdin="x")
        self.assertIn("unknown recipient", r.stderr)


class WakeTest(unittest.TestCase):
    def run_wake(self, home, command):
        env = {"HOME": home, "PATH": "/usr/bin:/bin", "SSH_ORIGINAL_COMMAND": command, "SSH_CLIENT": "100.1.2.3 5 22"}
        return subprocess.run([sys.executable, os.path.join(ROOT, "examples", "ssh-wake", "wake")],
                              env=env, capture_output=True, text=True)

    def test_wake_once_and_refuse_everything_else(self):
        home = tempfile.mkdtemp()
        self.assertEqual(self.run_wake(home, "wake 3 1").stdout.strip(), "queued")
        self.assertEqual(self.run_wake(home, "wake 1 3").stdout.strip(), "replay")
        for bad in ("ls", "wake", "wake 1;rm", "wake -1", "wake 1 $(id)"):
            self.assertEqual(self.run_wake(home, bad).returncode, 2, bad)
        time.sleep(0.5)
        queue = open(os.path.join(home, ".local/state/agent-doorbell/queue.txt")).read()
        self.assertEqual(queue.count("ids: 1, 3"), 1)


class GateTest(unittest.TestCase):
    def test_allow_list(self):
        home = tempfile.mkdtemp()
        gate = os.path.join(ROOT, "examples", "ssh-gate", "gate")
        run = lambda c, stdin="": subprocess.run([sys.executable, gate], input=stdin, capture_output=True, text=True,
                                                 env={"HOME": home, "SSH_ORIGINAL_COMMAND": c})
        self.assertEqual(run("health").returncode, 0)
        self.assertEqual(run("note topic-1", "hello").returncode, 0)
        self.assertEqual(run("note ../x", "hello").returncode, 2)
        self.assertEqual(run("bash -c id").returncode, 2)


if __name__ == "__main__":
    unittest.main()
