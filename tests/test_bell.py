"""Bell tests: fake webhook + temp bus.db. Standard library only (Python 3.11+)."""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BELL = os.path.join(ROOT, "bell", "bell.py")


class Hook(BaseHTTPRequestHandler):
    calls: list = []
    fail_next = 0

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Hook.calls.append({"auth": self.headers.get("Authorization"), "secret": self.headers.get("X-Secret"), "body": body})
        code = 500 if Hook.fail_next > 0 else 200
        Hook.fail_next = max(0, Hook.fail_next - 1)
        self.send_response(code)
        self.end_headers()

    def log_message(self, *a):
        pass


class BellTest(unittest.TestCase):
    def setUp(self):
        Hook.calls, Hook.fail_next = [], 0
        self.srv = HTTPServer(("127.0.0.1", 0), Hook)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.d = tempfile.mkdtemp()
        self.bus = os.path.join(self.d, "bus.db")
        self.conn = sqlite3.connect(self.bus, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT, recipient TEXT, "
                          "body TEXT, reply_to INTEGER, created_at TEXT, acked_at TEXT)")
        sec = os.path.join(self.d, "secrets")
        os.makedirs(sec)
        with open(os.path.join(sec, "alice.env"), "w") as f:
            f.write(f"URL=http://127.0.0.1:{self.srv.server_port}/hook\nKEY=test-key\n")
        with open(os.path.join(sec, "carol.env"), "w") as f:
            f.write(f"URL=http://127.0.0.1:{self.srv.server_port}/hook\nKEY=raw-key\nKEY_HEADER=X-Secret\n")
        with open(os.path.join(self.d, "config.toml"), "w") as f:
            f.write(f"""
[bell]
poll_seconds = 0.2
retry_seconds = [0.5, 0.5]
min_interval_seconds = 0
max_per_day = 3
message = "hi {{recipient}}: {{count}} new ({{ids}})"
[bell.targets.alice]
type = "webhook"
secret_file = "{sec}/alice.env"
text_field = "prompt"
extra = {{ routine = "inbox" }}
[bell.targets.bob]
type = "webhook"
secret_file = "{sec}/bob.env"
[bell.targets.carol]
type = "webhook"
secret_file = "{sec}/carol.env"
[bell.targets.dave]
type = "ssh"
secret_file = "{sec}/dave.env"
""")
        with open(os.path.join(sec, "dave.env"), "w") as f:
            f.write("SSH_HOST=bad host;rm\nSSH_USER=x\nSSH_KEY=/k\nSSH_KNOWN_HOSTS=/h\n")
        env = dict(os.environ, DOORBELL_CONFIG=os.path.join(self.d, "config.toml"), BELL_BUS_DB=self.bus,
                   BELL_STATE_DB=os.path.join(self.d, "state.db"))
        self.p = subprocess.Popen([sys.executable, "-I", BELL], env=env, stderr=subprocess.PIPE, text=True)
        time.sleep(0.8)

    def tearDown(self):
        self.p.terminate()
        self.log = self.p.communicate(timeout=5)[1]
        self.srv.shutdown()
        self.srv.server_close()
        self.assertNotIn("test-key", self.log)
        self.assertNotIn("raw-key", self.log)
        self.assertNotIn(str(self.srv.server_port), self.log)

    def send(self, to):
        return self.conn.execute("INSERT INTO messages (sender, recipient, body, created_at) VALUES ('x', ?, 'b', 'now')", (to,)).lastrowid

    def alice_calls(self):
        return [c for c in Hook.calls if c["body"]["recipient"] == "alice"]

    def test_idle_makes_no_calls(self):
        time.sleep(0.6)
        self.assertEqual(Hook.calls, [])

    def test_one_message_one_call_never_repeated(self):
        a = self.send("alice")
        time.sleep(1.2)
        calls = self.alice_calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["body"]["ids"], [a])
        self.assertEqual(calls[0]["auth"], "Bearer test-key")
        self.assertEqual(calls[0]["body"]["prompt"], f"hi alice: 1 new ({a})")
        self.assertEqual(calls[0]["body"]["routine"], "inbox")
        time.sleep(0.8)
        self.assertEqual(len(self.alice_calls()), 1)

    def test_custom_header(self):
        self.send("carol")
        time.sleep(1.2)
        self.assertEqual([(c["auth"], c["secret"]) for c in Hook.calls], [(None, "raw-key")])

    def test_member_without_secret_is_off(self):
        self.send("bob")
        time.sleep(1)
        self.assertEqual(Hook.calls, [])

    def test_invalid_ssh_secret_is_off(self):
        self.send("dave")
        time.sleep(1)
        self.p.terminate()
        log = self.p.communicate(timeout=5)[1]
        self.assertIn("dave: off (bad SSH_USER or SSH_HOST)", log)
        self.p = subprocess.Popen(["true"], stderr=subprocess.PIPE, text=True)

    def test_retry_then_success_only_new_ids(self):
        a = self.send("alice")
        time.sleep(1.2)
        Hook.fail_next = 1
        b = self.send("alice")
        time.sleep(2)
        calls = self.alice_calls()
        self.assertEqual([c["body"]["ids"] for c in calls], [[a], [b], [b]])

    def test_acked_during_backoff_is_dropped(self):
        Hook.fail_next = 99
        c = self.send("alice")
        time.sleep(0.6)
        self.conn.execute("UPDATE messages SET acked_at = 'now' WHERE id = ?", (c,))
        n = len(Hook.calls)
        time.sleep(1.5)
        self.assertEqual(len(Hook.calls), n)

    def test_daily_cap(self):
        for _ in range(5):
            self.send("alice")
            time.sleep(0.6)
        time.sleep(0.5)
        self.assertEqual(len(self.alice_calls()), 3)


if __name__ == "__main__":
    unittest.main()
