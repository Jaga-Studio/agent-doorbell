#!/usr/bin/env python3
"""agent-doorbell setup, called by ./setup.sh. Standard library only, Python 3.11+.

  (no flag)        create config.toml if missing, issue tokens, install, start, tailscale serve
  --docker         run with Docker Compose instead of a background service
  --restart        restart (after adding members or editing config.toml)
  --status         show whether it is running
  --stop           stop and remove the background service

Unattended use: --members "assistant:connector,commander:webhook,coder:ssh" --host NAME
                --port N --no-start --no-serve --lang en|ja
"""
from __future__ import annotations

import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import manage  # noqa: E402

ROOT = manage.ROOT
CONFIG = manage.CONFIG
TOKENS = manage.DEFAULT_TOKENS
RUNTIME = os.path.join(ROOT, ".runtime.json")
VENV_PY = os.path.join(ROOT, ".venv", "bin", "python")
LABEL = "io.github.agent-doorbell"
UNIT = "doorbell"
KINDS = {
    "1": "connector", "connector": "connector",
    "2": "webhook", "webhook": "webhook",
    "3": "ssh", "ssh": "ssh",
}
RECIPES = {
    "connector": "docs/recipes/hosted-mcp-assistant.md",
    "webhook": "docs/recipes/webhook-routines.md",
    "cli": "docs/recipes/claude-code.md",
}
INTERACTIVE = sys.stdin.isatty()


def say(msg: str = "") -> None:
    print(msg, flush=True)


def ask(question: str, default: str = "") -> str:
    if not INTERACTIVE:
        return default
    answer = input(f"{question}{f' [{default}]' if default else ''}: ").strip()
    return answer or default


def yes(question: str, default: bool = True) -> bool:
    a = ask(question + (" (Y/n)" if default else " (y/N)"), "y" if default else "n")
    return a.lower().startswith("y")


def run(cmd: list[str], check: bool = True, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, text=True, **kw)


def flag(argv: list[str], name: str, value: bool = False):
    argv, v = manage.take_flag(argv, name, value)
    return argv, v


# ---------- config ----------

def tailscale_bin() -> str | None:
    for c in ("tailscale", "/Applications/Tailscale.app/Contents/MacOS/Tailscale"):
        if shutil.which(c) or os.path.exists(c):
            return shutil.which(c) or c
    return None


def tailnet_name() -> str | None:
    ts = tailscale_bin()
    if not ts:
        return None
    try:
        out = run([ts, "status", "--json"], capture_output=True, timeout=10).stdout
        return json.loads(out)["Self"]["DNSName"].rstrip(".") or None
    except Exception:
        return None


def collect_members(spec: str | None) -> dict[str, str]:
    members: dict[str, str] = {}
    if spec:
        for item in spec.split(","):
            name, _, kind = item.strip().partition(":")
            members[name] = KINDS.get(kind or "connector") or sys.exit(f"unknown kind {kind!r}")
        return members
    if not INTERACTIVE:
        sys.exit("no config.toml: pass --members name:kind,... or run in a terminal")
    say("Name your agents (letters, digits, - and _). Others will use the name in send(to=...).")
    say("How does each one get woken up?")
    say("  1) it checks its inbox on its own   (hosted assistant with a custom MCP connector)")
    say("  2) webhook                          (agent whose routines start from a webhook URL)")
    say("  3) SSH                              (Claude Code or another CLI agent on a computer)")
    while True:
        name = ask(f"Agent {len(members) + 1} name (empty when done)")
        if not name:
            if len(members) >= 2:
                return members
            say("At least two agents are needed.")
            continue
        if not name.replace("-", "").replace("_", "").isalnum():
            say("Letters, digits, - and _ only.")
            continue
        kind = KINDS.get(ask(f"How is {name} woken up? 1/2/3", "1"))
        if not kind:
            say("Answer 1, 2 or 3.")
            continue
        members[name] = kind


def write_config(members: dict[str, str], host: str | None, port: int) -> None:
    hosts = ([f"{host}", f"{host}:443"] if host else []) + [f"127.0.0.1:{port}"]
    lines = [
        "# agent-doorbell configuration (written by ./setup.sh; edit freely, then ./setup.sh --restart).",
        "# Secrets never go here. Relative paths are relative to this folder.",
        "",
        "[bus]",
        f"allowed_hosts = {json.dumps(hosts)}",
        "max_body_chars = 20000",
        "max_pending_per_recipient = 500",
        "acked_retention_days = 30",
        "",
        "# One table per agent. Add can_send_to = [\"a\", \"b\"] to limit whom it may write to.",
    ]
    for name in members:
        lines.append(f"[members.{name}]")
    lines += [
        "",
        "[bell]",
        "poll_seconds = 5",
        "min_interval_seconds = 60   # at most one wake-up per agent per minute; later messages are batched",
        "max_per_day = 40            # stops two agents from waking each other forever",
        "retry_seconds = [30, 60, 120, 300, 600]",
        "timeout_seconds = 15",
    ]
    for name, kind in members.items():
        if kind == "connector":
            continue
        lines += ["", f"[bell.targets.{name}]", f'type = "{kind}"', f'secret_file = "secrets/bell/{name}.env"']
    with open(CONFIG, "w") as f:
        f.write("\n".join(lines) + "\n")


def config_members(cfg: dict) -> dict[str, str]:
    return {name: manage.kind_of(cfg, name) for name in cfg.get("members", {})}


# ---------- runtime ----------

def load_runtime() -> dict:
    try:
        with open(RUNTIME) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def pick_mode(docker: bool) -> str:
    if docker:
        return "docker"
    if platform.system() == "Darwin":
        return "launchd"
    if shutil.which("systemctl") and run(["systemctl", "--user", "show-environment"], check=False,
                                          capture_output=True).returncode == 0:
        return "systemd"
    return "manual"


def install_python_deps() -> None:
    ok = os.path.exists(VENV_PY) and run([VENV_PY, "-c", "import mcp, uvicorn"], check=False,
                                         capture_output=True).returncode == 0
    if ok:
        return
    say("Installing the bus's two Python packages into .venv ...")
    req = os.path.join(ROOT, "bus", "requirements.txt")
    if shutil.which("uv"):
        run(["uv", "venv", "--quiet", "--allow-existing", "--python", "3.12", os.path.join(ROOT, ".venv")])
        run(["uv", "pip", "install", "--quiet", "--python", VENV_PY, "-r", req])
    else:
        run([sys.executable, "-m", "venv", os.path.join(ROOT, ".venv")])
        run([VENV_PY, "-m", "pip", "install", "--quiet", "-r", req])


def service_env(port: int) -> dict[str, str]:
    return {"DOORBELL_HOME": ROOT, "BUS_PORT": str(port), "PYTHONUNBUFFERED": "1"}


def launchd_plist(part: str) -> str:
    return os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.{part}.plist")


def launchd_start(port: int) -> None:
    domain = f"gui/{os.getuid()}"
    os.makedirs(os.path.dirname(launchd_plist("bus")), exist_ok=True)
    for part, script in (("bus", "bus/server.py"), ("bell", "bell/bell.py")):
        path = launchd_plist(part)
        with open(path, "wb") as f:
            plistlib.dump({
                "Label": f"{LABEL}.{part}",
                "ProgramArguments": [VENV_PY, os.path.join(ROOT, script)],
                "WorkingDirectory": ROOT,
                "EnvironmentVariables": service_env(port),
                "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 10,
                "StandardOutPath": os.path.join(ROOT, "logs", f"{part}.log"),
                "StandardErrorPath": os.path.join(ROOT, "logs", f"{part}.log"),
            }, f)
        run(["launchctl", "bootout", f"{domain}/{LABEL}.{part}"], check=False, capture_output=True)
        run(["launchctl", "bootstrap", domain, path])


def launchd_stop() -> None:
    for part in ("bus", "bell"):
        run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}.{part}"], check=False, capture_output=True)
        if os.path.exists(launchd_plist(part)):
            os.remove(launchd_plist(part))


def systemd_start(port: int) -> None:
    unit_dir = os.path.expanduser("~/.config/systemd/user")
    os.makedirs(unit_dir, exist_ok=True)
    env = " ".join(f'"{k}={v}"' for k, v in service_env(port).items())
    for part, script in (("bus", "bus/server.py"), ("bell", "bell/bell.py")):
        with open(os.path.join(unit_dir, f"{UNIT}-{part}.service"), "w") as f:
            f.write(
                f"[Unit]\nDescription=agent-doorbell {part}\nAfter=network-online.target\n\n"
                f"[Service]\nEnvironment={env}\nWorkingDirectory=\"{ROOT}\"\n"
                f"ExecStart=\"{VENV_PY}\" \"{os.path.join(ROOT, script)}\"\nRestart=always\nRestartSec=10\n\n"
                f"[Install]\nWantedBy=default.target\n"
            )
    run(["systemctl", "--user", "daemon-reload"])
    run(["systemctl", "--user", "enable", "--now", f"{UNIT}-bus", f"{UNIT}-bell"], capture_output=True)
    run(["systemctl", "--user", "restart", f"{UNIT}-bus", f"{UNIT}-bell"])
    if run(["loginctl", "enable-linger"], check=False, capture_output=True).returncode != 0:
        say(f"Note: to keep it running after you log out, run once:  sudo loginctl enable-linger {os.environ.get('USER', '$USER')}")


def systemd_stop() -> None:
    run(["systemctl", "--user", "disable", "--now", f"{UNIT}-bus", f"{UNIT}-bell"], check=False, capture_output=True)
    for part in ("bus", "bell"):
        p = os.path.expanduser(f"~/.config/systemd/user/{UNIT}-{part}.service")
        if os.path.exists(p):
            os.remove(p)
    run(["systemctl", "--user", "daemon-reload"], check=False)


def compose() -> list[str]:
    if run(["docker", "compose", "version"], check=False, capture_output=True).returncode == 0:
        return ["docker", "compose"]
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    sys.exit("Docker Compose not found. Run ./setup.sh without --docker to use a background service instead.")


def docker_start(port: int, restart: bool) -> None:
    with open(os.path.join(ROOT, ".env"), "w") as f:
        f.write(f"DOORBELL_UID={os.getuid()}\nDOORBELL_GID={os.getgid()}\nDOORBELL_PORT={port}\n")
    run(compose() + ["up", "-d", "--build"], cwd=ROOT)
    if restart:
        run(compose() + ["restart"], cwd=ROOT)


def start(mode: str, port: int, restart: bool = False) -> None:
    if mode == "docker":
        docker_start(port, restart)
        return
    install_python_deps()
    if mode == "launchd":
        launchd_start(port)
    elif mode == "systemd":
        systemd_start(port)
    else:
        say("No launchd or systemd here. Start these two yourself (e.g. under tmux or your init system):")
        env = " ".join(f"{k}='{v}'" for k, v in service_env(port).items())
        say(f"  {env} '{VENV_PY}' '{ROOT}/bus/server.py'")
        say(f"  {env} '{VENV_PY}' '{ROOT}/bell/bell.py'")


def stop(mode: str) -> None:
    {"launchd": launchd_stop, "systemd": systemd_stop}.get(mode, lambda: None)()
    if mode == "docker":
        run(compose() + ["down"], cwd=ROOT)


def bus_alive(port: int, token: str | None = None, wait: float = 20) -> str:
    """'ok' (token accepted), 'up' (answers, no token tried) or 'down'."""
    url = f"http://127.0.0.1:{port}/mcp"
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "inbox", "arguments": {"limit": 1}}}).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": "2025-06-18"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    deadline = time.time() + wait
    while True:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=5) as r:
                return "ok" if "error" not in json.loads(r.read()) else "up"
        except urllib.error.HTTPError as e:
            if e.code == 401 and not token:
                return "up"
        except (urllib.error.URLError, OSError):
            pass
        if time.time() > deadline:
            return "down"
        time.sleep(1)


def logs_hint(mode: str) -> str:
    return {
        "launchd": f"{ROOT}/logs/bus.log and logs/bell.log",
        "systemd": "journalctl --user -u doorbell-bus -u doorbell-bell",
        "docker": "docker logs doorbell-bus / docker logs doorbell-bell",
    }.get(mode, "the terminals you started them in")


def tailscale_serve(port: int) -> bool:
    ts = tailscale_bin()
    target = f"http://127.0.0.1:{port}"
    cmd_text = f"tailscale serve --bg --https=443 {target}"
    if not ts:
        say(f"Tailscale not found. Install it, then run:  {cmd_text}")
        return False
    if not yes(f"Put the bus on your tailnet now ({cmd_text})? Tailnet only, nothing public", True):
        say(f"Skipped. Run later:  {cmd_text}")
        return False
    r = run([ts, "serve", "--bg", "--https=443", target], check=False, capture_output=True)
    if r.returncode != 0:
        say(f"tailscale serve failed: {r.stderr.strip()[:300]}")
        say(f"On Linux it may need:  sudo tailscale set --operator=$USER  then  {cmd_text}")
        return False
    return True


# ---------- main ----------

def main(argv: list[str]) -> None:
    argv, docker = flag(argv, "--docker")
    argv, restart = flag(argv, "--restart")
    argv, stop_ = flag(argv, "--stop")
    argv, status = flag(argv, "--status")
    argv, no_start = flag(argv, "--no-start")
    argv, no_serve = flag(argv, "--no-serve")
    argv, members_spec = flag(argv, "--members", True)
    argv, host = flag(argv, "--host", True)
    argv, port = flag(argv, "--port", True)
    argv, lang = flag(argv, "--lang", True)
    if argv:
        sys.exit(__doc__)
    rt = load_runtime()
    port = int(port or rt.get("port", 8765))
    lang = lang or ("ja" if os.environ.get("LANG", "").startswith("ja") else "en")

    if stop_ or status or restart:
        if not rt:
            sys.exit("Not set up yet. Run ./setup.sh first.")
        if stop_:
            stop(rt["mode"])
            os.remove(RUNTIME)
            say("Stopped. Your data, config.toml and secrets/ are untouched.")
        elif restart:
            start(rt["mode"], rt["port"], restart=True)
            say(f"Restarted: bus {bus_alive(rt['port'])}. Logs: {logs_hint(rt['mode'])}")
        else:
            say(f"mode {rt['mode']}, port {rt['port']}: bus {bus_alive(rt['port'], wait=0)}")
        return

    # 1. config
    if os.path.exists(CONFIG):
        say("Using the existing config.toml.")
    else:
        members = collect_members(members_spec)
        if not host:
            host = tailnet_name()
            if host:
                say(f"This machine's tailnet name: {host}")
            else:
                host = ask("This machine's tailnet name (machine.your-tailnet.ts.net; empty = local only)") or None
        write_config(members, host, port)
        say("Wrote config.toml.")
    cfg = manage.read_config()
    members = config_members(cfg)

    # 2. folders
    for d, mode in (("data", 0o700), ("bell-state", 0o700), ("logs", 0o700), ("secrets", 0o700),
                    (os.path.join("secrets", "bell"), 0o700)):
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)
        os.chmod(os.path.join(ROOT, d), mode)

    # 3. tokens for members that have none
    have = set(manage.load(TOKENS).values())
    new_tokens = {name: manage.new_token(TOKENS, name) for name in members if name not in have}

    # 4. start
    mode = rt.get("mode") or pick_mode(bool(docker))
    if no_start:
        say("Not started (--no-start).")
    else:
        start(mode, port, restart=bool(rt))
        with open(RUNTIME, "w") as f:
            json.dump({"mode": mode, "port": port}, f)
        first = next(iter(new_tokens.values()), None)
        state = bus_alive(port, first)
        say(f"Bus: {'running' if state != 'down' else 'NOT answering'} (mode {mode}). Logs: {logs_hint(mode)}")
        if state == "down":
            sys.exit(1)
        if not no_serve:
            tailscale_serve(port)

    # 5. hand-off per agent
    say("\n=== Next: connect each agent ===")
    say(f"Endpoint: {manage.endpoint(cfg)}")
    for name, kind in members.items():
        say(f"\n--- {name} ({kind}) ---  guide: {RECIPES[kind]}")
        if name in new_tokens:
            say(f"Token (shown once; put it in the agent's secret field or a chmod 600 file, never in chat):\n  {new_tokens[name]}")
        else:
            say("Token: already issued earlier (lost it? tools/manage.py member rotate " + name + ")")
        if kind != "connector":
            say(f"Wake-up: run tools/set-secret.sh {'webhook' if kind == 'webhook' else 'ssh'} {name}"
                + ("  (after the agent has created its routine)" if kind == "webhook" else "  (see the guide)"))
        text = manage.render_prompt(cfg, name, lang)
        if INTERACTIVE and yes(f"Copy the prompt for {name} to the clipboard?", True) and manage.copy_to_clipboard(text):
            say("Copied. Paste it to the agent.")
        else:
            say("Prompt to give the agent:\n" + text)
    say("\nAny time later: tools/manage.py prompt <name> --copy")


if __name__ == "__main__":
    main(sys.argv[1:])
