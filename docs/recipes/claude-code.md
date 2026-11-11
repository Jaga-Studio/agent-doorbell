# Recipe: Claude Code (or any CLI agent) on your own machine

Claude Code can talk to the bus with the CLI, and the bell can wake it over SSH. Each wake-up is one headless run, and only when a message arrives.

## 1. Talk to the bus

```sh
python3 tools/manage.py member add coder        # on the bus host; copy the token
mkdir -p ~/.config/doorbell && chmod 700 ~/.config/doorbell
pbpaste > ~/.config/doorbell/coder.token && chmod 600 ~/.config/doorbell/coder.token   # macOS; or use an editor
cp cli/doorbell ~/.local/bin/doorbell
export DOORBELL_URL=https://<machine>.<tailnet>.ts.net/mcp DOORBELL_TOKEN_FILE=~/.config/doorbell/coder.token
doorbell inbox
```

The CLI needs only Python 3.9+. Put the two `export` lines in your shell profile.

Prefer MCP instead? `claude mcp add --transport http doorbell https://<machine>.<tailnet>.ts.net/mcp --header "Authorization: Bearer <token>"` works too, but stores the token in Claude Code's config file. The CLI keeps it in one `chmod 600` file.

## 2. Let the bell wake it

On **the machine where Claude Code runs**:

1. Install the forced command:
   ```sh
   cp examples/ssh-wake/wake ~/.local/bin/doorbell-wake && chmod 755 ~/.local/bin/doorbell-wake
   ```
   Edit `WAKE_COMMAND` in it. For one headless Claude Code turn that may only use the CLI, point it at a small wrapper script that sets `DOORBELL_URL` / `DOORBELL_TOKEN_FILE` and runs
   `claude -p --allowedTools "Bash(doorbell:*)"` (the prompt arrives on stdin). If you already run a long-lived agent with its own queue, append to that queue instead (that is what we do).

On **the bus host**:

2. Create the bell's key (it never leaves the bus host) and pin your machine's host key:
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

In `config.toml`:

```toml
[bell.targets.coder]
type = "ssh"
secret_file = "/secrets/bell/coder.env"
```

## 3. Test

Send `coder` one message. `~/.local/state/agent-doorbell/wake.log` shows one `wake [...]` line from the bus host's IP, and your agent runs once. Sending `ls` as the SSH command is refused.

## Usage estimate

One headless run per batch of messages (batched at most once a minute, capped per day). Idle: nothing.
