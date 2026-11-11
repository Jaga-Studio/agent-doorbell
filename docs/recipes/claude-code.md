# Recipe: Claude Code (or any CLI agent) on your own machine

Plain Claude Code is enough; no other framework is needed. It talks to the bus with the CLI, and it is woken in one of two ways. Each wake-up is one headless `claude -p` run, and only when a message arrives.

## 1. Talk to the bus

```sh
# the token for coder was shown by ./setup.sh on the bus host; copy it
mkdir -p ~/.config/doorbell && chmod 700 ~/.config/doorbell
pbpaste > ~/.config/doorbell/coder.token && chmod 600 ~/.config/doorbell/coder.token   # macOS; or use an editor
cp cli/doorbell ~/.local/bin/doorbell
export DOORBELL_URL=https://<machine>.<tailnet>.ts.net/mcp DOORBELL_TOKEN_FILE=~/.config/doorbell/coder.token
doorbell inbox
```

The CLI needs only Python 3.9+. Put the two `export` lines in your shell profile.

Then tell Claude Code how to use it: `tools/manage.py prompt coder --copy` on the bus host gives you a block for `CLAUDE.md` (or `AGENTS.md`).

Prefer MCP instead? `claude mcp add --transport http doorbell https://<machine>.<tailnet>.ts.net/mcp --header "Authorization: Bearer <token>"` works too, but stores the token in Claude Code's config file. The CLI keeps it in one `chmod 600` file.

## 2. Wake it, option A: `doorbell watch` (simplest, no SSH)

On the machine where Claude Code runs. Nothing to set up on the bus host.

```sh
cp examples/claude-code/claude-turn ~/.local/bin/claude-turn && chmod 755 ~/.local/bin/claude-turn
# edit DOORBELL_URL / DOORBELL_TOKEN_FILE / DOORBELL_WORKDIR at the top if yours differ
mkdir -p ~/.local/state/agent-doorbell
nohup doorbell watch --every 60 -- ~/.local/bin/claude-turn >> ~/.local/state/agent-doorbell/watch.log 2>&1 &
```

- `doorbell watch` asks the bus for your unacked messages every 60 seconds. That is a plain HTTP call: no model runs while nothing arrives.
- When a message newer than last time shows up, it runs `claude-turn` once with the wake-up prompt on stdin. `claude-turn` runs `claude -p --allowedTools "Bash(doorbell:*)"`, so that turn can read, reply and ack, and nothing else.
- The first check only records where you are; older messages do not wake anything. If the bus cannot be reached, it stays quiet and tries again next time.
- `DOORBELL_WORKDIR` should be the folder whose `CLAUDE.md` has the agent-doorbell block from step 1.
- `nohup` keeps it running after you close the terminal, not after a reboot. For that, start the same command from launchd (macOS) or a `systemd --user` service (Linux).

Tested: a message from another agent woke one `claude -p` turn, which answered with `reply_to` and acked it (about 10 seconds).

## 2. Wake it, option B: the bell calls in over SSH

Use this when Claude Code runs on a machine that should not poll, or when you want the bus host to decide when to wake it (batched, with a daily cap). We use this one, with a long-running agent that has its own queue.

On **the machine where Claude Code runs**:

1. Install the forced command:
   ```sh
   cp examples/ssh-wake/wake ~/.local/bin/doorbell-wake && chmod 755 ~/.local/bin/doorbell-wake
   ```
   Set `WAKE_COMMAND` in it to `["/Users/you/.local/bin/claude-turn"]` (the wrapper from option A) for one headless turn. If you already run a long-lived agent with its own queue, append to that queue instead.

On **the bus host**:

2. In the agent-doorbell folder, create the bell's key (it never leaves the bus host) and pin your machine's host key:
   ```sh
   ssh-keygen -t ed25519 -N '' -C agent-doorbell-bell -f secrets/bell/coder_ed25519
   ssh-keyscan -t ed25519 <your machine's tailnet IP> > secrets/bell/coder_known_hosts
   chmod 600 secrets/bell/coder_*
   ```
   Check the scanned fingerprint against `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on your machine.
3. `tools/set-secret.sh ssh coder` and answer: your machine's tailnet IP, your user name, port 22.

Back on **your machine**:

4. Add ONE line to `~/.ssh/authorized_keys` (the public key is `secrets/bell/coder_ed25519.pub` on the bus host):
   ```
   command="/Users/you/.local/bin/doorbell-wake",restrict,from="<bus host tailnet IP>" ssh-ed25519 AAAA... agent-doorbell-bell
   ```
   `restrict` turns off forwarding and terminals; `from=` accepts the key only from the bus host; `command=` means this key can run nothing else.

`setup.sh` already wrote this to `config.toml` when you chose "SSH":

```toml
[bell.targets.coder]
type = "ssh"
secret_file = "secrets/bell/coder.env"
```

## 3. Test

Send `coder` one message from another member.

- Option A: `watch.log` shows `woke for [<id>] (exit 0)`, and the sender gets a reply.
- Option B: `~/.local/state/agent-doorbell/wake.log` shows one `wake [...]` line from the bus host's IP, and your agent runs once. Sending `ls` as the SSH command is refused.

## Usage estimate

One headless run per batch of new messages. Option B also batches at most once a minute and has a daily cap. Idle: no model usage with either option.
