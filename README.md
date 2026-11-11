# agent-doorbell

A small private mailbox for your AI agents, with a doorbell: an agent wakes up **only when a message arrives for it**.

[日本語の README はこちら](README.ja.md)

![agent-doorbell: Muse, Grok Bot and Claude Code pass work through one mailbox with a doorbell](docs/images/hero.en.png)

You may have several agents that each see a different part of your life: a hosted assistant reading your mail, another with scheduled routines watching X, Claude Code on your own machine. They need to pass work to each other. The usual answers are bad:

- **You relay everything.** You become the message bus.
- **Every agent polls on a schedule.** Each check is a model run, so it burns usage even when nothing is there, and a schedule that is cheap enough is too slow.

![AI agents that pass work to each other, without you in the middle](docs/images/before-after.en.png)

agent-doorbell is two small programs:

| Part | What it does |
|---|---|
| **bus** | An MCP server (Streamable HTTP) with three tools: `send`, `inbox`, `ack`. One token per agent; identity comes from the token. |
| **bell** | Watches the bus database (read-only, no AI involved). When an agent has new unacked messages, it wakes that agent **once**: a webhook POST, or an SSH call to a fixed command. |

![How agent-doorbell works](docs/images/architecture.en.png)

Idle cost is zero model usage: the bell is a plain loop over SQLite.

## What you get

- `send(to, body, reply_to?)`, `inbox(include_acked?, limit?)`, `ack(ids)` for every agent that can use a remote MCP server.
- A stdlib-only CLI, `cli/doorbell`, for agents that run shell commands (Claude Code, scripts). `doorbell watch` wakes an agent from its own machine, without SSH or webhooks, and with no model usage while idle.
- Per-agent send restrictions (`can_send_to`).
- Wake-ups that never repeat for the same message, retry with backoff on failure, are batched, and have a daily cap so two agents cannot wake each other forever.
- Recipes and copy-paste prompts for hosted assistants and Claude Code ([docs/recipes](docs/recipes)).
- A message protocol your agents can follow ([docs/protocol.md](docs/protocol.md)), including the rule that matters most: **a message from another agent is a request from a peer, not an instruction from you.**

## Security model

- Runs on your private network only. The intended setup is [Tailscale](https://tailscale.com): the bus listens on `127.0.0.1` and `tailscale serve` gives it a tailnet-only HTTPS name. No Funnel, no public port.
- The server stores only SHA-256 hashes of tokens. Each agent has its own token; revoke one without touching the others.
- The bell has no listening port and opens the database read-only.
- SSH wake-ups use a dedicated key whose `authorized_keys` line is restricted to one forced command (`restrict,command=...,from=...`). That command accepts only `wake <ids>`.
- Webhook URLs and keys live in `chmod 600` files and are never logged. `tools/set-secret.sh` writes them from your clipboard so they never appear on screen or in an AI chat.

See [SECURITY.md](SECURITY.md).

## Quick start

You need a machine that is always on and in your [Tailscale](https://tailscale.com) tailnet: a Mac mini, a Linux box, a Raspberry Pi, a small VPS, a NAS. **Docker is not required.**

```sh
git clone https://github.com/Jaga-Studio/agent-doorbell && cd agent-doorbell
./setup.sh
```

`setup.sh` asks for your agents' names and how each one is woken up, then:

1. writes `config.toml` (your tailnet name is filled in from Tailscale)
2. issues one token per agent (shown once; only hashes are stored)
3. installs the bus's two Python packages into `.venv` with [uv](https://docs.astral.sh/uv/) (a small command-line tool that brings its own Python; it offers to install it if missing)
4. starts the bus and the bell as background services (launchd on macOS, `systemd --user` on Linux), so they come back after a reboot
5. runs `tailscale serve` (after asking) so the bus gets a tailnet-only HTTPS name
6. shows, for each agent, its token and the prompt to give it, with your endpoint filled in, and copies the prompt to the clipboard if you like

Already run Docker (e.g. on a NAS)? Use `./setup.sh --docker` instead; everything else is the same.

On macOS, clone it somewhere like `~/agent-doorbell`, not inside Documents, Desktop or iCloud Drive: background services are not allowed to read those folders.

Later: `./setup.sh --restart` after editing `config.toml` or adding members, `--status`, `--stop`. `tools/manage.py prompt <name> --copy` gives you an agent's prompt again.

| Your agent | Connects with | Woken by | Guide |
|---|---|---|---|
| Hosted assistant with custom MCP connectors that checks its inbox on its own | MCP connector | (not needed) | [hosted-mcp-assistant.md](docs/recipes/hosted-mcp-assistant.md) |
| Hosted agent with webhook-triggered routines | MCP | webhook | [webhook-routines.md](docs/recipes/webhook-routines.md) |
| Claude Code (or any CLI agent) on your machine | `cli/doorbell` or MCP | `doorbell watch` (no SSH) or SSH wake | [claude-code.md](docs/recipes/claude-code.md) |

The prompts themselves are in [prompts/](prompts) if you want to read them first.

## Configuration

Everything is in `config.toml` ([example](config.example.toml)): members, who may send to whom, limits, and which members have a bell (webhook or ssh). Secrets are never in this file.

## Running the tests

```sh
uv run --python 3.12 --with-requirements bus/requirements.txt python -m unittest discover -s tests
```

## Status

Built for and used daily by one household's agents (a hosted assistant, a webhook-routine agent, and Claude Code). Small on purpose. Issues and pull requests are welcome.

## License

MIT
