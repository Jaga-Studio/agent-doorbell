#!/usr/bin/env python3
"""Manage member tokens (Python 3.9+, standard library only).

  manage.py member add <name>      create a token, print it ONCE, store only its SHA-256 hash
  manage.py member rotate <name>   replace a member's token (old one stops working after a bus restart)
  manage.py member remove <name>   delete a member's token
  manage.py member list            members that have a token

Options: --tokens PATH (default ./secrets/tokens.json)
The member must also be listed in config.toml. Restart the bus after any change.
Hand the printed token to the agent through its own secret field, never through chat.
"""
import hashlib
import json
import os
import re
import secrets
import sys
import tempfile


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save(path, data):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def main(argv):
    path = "secrets/tokens.json"
    if "--tokens" in argv:
        i = argv.index("--tokens")
        path = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if len(argv) < 2 or argv[0] != "member":
        sys.exit(__doc__)
    action, name = argv[1], (argv[2] if len(argv) > 2 else None)
    data = load(path)
    if action == "list":
        for member in sorted(set(data.values())):
            print(member)
        return
    if not name or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        sys.exit("give a member name (letters, digits, - and _)")
    has = name in data.values()
    if action == "remove":
        if not has:
            sys.exit(f"{name} has no token")
        save(path, {h: m for h, m in data.items() if m != name})
        print(f"removed {name}; restart the bus")
        return
    if action == "add" and has:
        sys.exit(f"{name} already has a token; use rotate")
    if action == "rotate" and not has:
        sys.exit(f"{name} has no token; use add")
    if action not in ("add", "rotate"):
        sys.exit(__doc__)
    tok = secrets.token_urlsafe(32)
    data = {h: m for h, m in data.items() if m != name}
    data[hashlib.sha256(tok.encode()).hexdigest()] = name
    save(path, data)
    print(f"Token for {name} (shown once, store it in the agent's secret field or a chmod 600 file):", file=sys.stderr)
    print(tok)
    print("Restart the bus to load it.", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
