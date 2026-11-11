"""examples/ssh-gate/gate: allow-list and the skipped leading gate name."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

GATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "ssh-gate", "gate")


def call(cmd):
    env = dict(os.environ, HOME=tempfile.mkdtemp(), SSH_ORIGINAL_COMMAND=cmd)
    r = subprocess.run([sys.executable, GATE], env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return r.returncode, json.loads(r.stdout)


class GateTest(unittest.TestCase):
    def test_same_command_line_before_and_after_restricting(self):
        for cmd in ("health", "agent-gate health", "/home/x/.local/bin/agent-gate health"):
            self.assertEqual(call(cmd)[1]["ok"], True, cmd)

    def test_everything_else_is_refused(self):
        for cmd in ("echo test", "agent-gate echo test", "", "'unbalanced", "health; rm -rf /"):
            code, out = call(cmd)
            self.assertEqual((code, "error" in out), (2, True), cmd)


if __name__ == "__main__":
    unittest.main()
