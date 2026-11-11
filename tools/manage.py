#!/usr/bin/env python3
"""Manage members (standard library only; `prompt` needs Python 3.11+).

  manage.py member add <name>      create a token, print it ONCE, store only its SHA-256 hash
  manage.py member rotate <name>   replace a member's token
  manage.py member remove <name>   delete a member's token
  manage.py member list            members that have a token
  manage.py prompt <name> [--lang en|ja] [--copy]
                                   the text to give that agent, with your endpoint filled in;
                                   --copy puts it on the clipboard instead of printing it

Options: --tokens PATH (default secrets/tokens.json in this checkout)
The member must also be listed in config.toml. After add/rotate/remove run ./setup.sh --restart.
Hand the printed token to the agent through its own secret field, never through chat.
"""
import hashlib
import json
import os
import re
import secrets
import shutil
import string
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TOKENS = os.path.join(ROOT, "secrets", "tokens.json")
CONFIG = os.path.join(ROOT, "config.toml")


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


def new_token(path, name):
    """Create or replace name's token; return the token (the file keeps only its hash)."""
    tok = secrets.token_urlsafe(32)
    data = {h: m for h, m in load(path).items() if m != name}
    data[hashlib.sha256(tok.encode()).hexdigest()] = name
    save(path, data)
    return tok


def endpoint(cfg):
    hosts = [h for h in cfg.get("bus", {}).get("allowed_hosts", []) if not h.startswith("127.0.0.1")]
    if not hosts:
        return "http://127.0.0.1:8765/mcp"
    return f"https://{hosts[0].split(':')[0]}/mcp"


def kind_of(cfg, name):
    target = cfg.get("bell", {}).get("targets", {}).get(name)
    if target is None:
        return "connector"
    return "cli" if target.get("type") == "ssh" else "webhook"


def render_prompt(cfg, name, lang="en"):
    members = cfg.get("members", {})
    if name not in members:
        sys.exit(f"{name} is not a member in config.toml")
    allowed = members[name].get("can_send_to")
    peers = [m for m in members if m != name and (allowed is None or m in allowed)]
    with open(os.path.join(ROOT, "prompts", lang, kind_of(cfg, name) + ".txt"), encoding="utf-8") as f:
        tpl = string.Template(f.read())
    return tpl.substitute(name=name, url=endpoint(cfg), peers=", ".join(peers))


def read_config(path=CONFIG):
    import tomllib  # Python 3.11+
    with open(path, "rb") as f:
        return tomllib.load(f)


def copy_to_clipboard(text):
    for cmd in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, input=text.encode(), check=True)
            return True
    return False


def take_flag(argv, flag, has_value):
    if flag not in argv:
        return argv, None
    i = argv.index(flag)
    value = argv[i + 1] if has_value else True
    return argv[:i] + argv[i + (2 if has_value else 1):], value


def main(argv):
    argv, path = take_flag(argv, "--tokens", True)
    path = path or DEFAULT_TOKENS
    if len(argv) >= 2 and argv[0] == "prompt":
        argv, lang = take_flag(argv, "--lang", True)
        argv, copy = take_flag(argv, "--copy", False)
        text = render_prompt(read_config(), argv[1], lang or "en")
        if copy and copy_to_clipboard(text):
            print(f"Copied the prompt for {argv[1]} to the clipboard.", file=sys.stderr)
        else:
            print(text)
        return
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
        print(f"removed {name}; run ./setup.sh --restart")
        return
    if action == "add" and has:
        sys.exit(f"{name} already has a token; use rotate")
    if action == "rotate" and not has:
        sys.exit(f"{name} has no token; use add")
    if action not in ("add", "rotate"):
        sys.exit(__doc__)
    tok = new_token(path, name)
    print(f"Token for {name} (shown once, store it in the agent's secret field or a chmod 600 file):", file=sys.stderr)
    print(tok)
    print("Then run ./setup.sh --restart to load it.", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
