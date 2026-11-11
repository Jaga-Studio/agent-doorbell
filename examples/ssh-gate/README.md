# SSH gate pattern

[日本語](README.ja.md)

`gate` is a template, not part of the bus. Use it when a remote agent needs to do a few fixed things on your machine (read a status, drop a note) and must not get a shell. See the docstring at the top of `gate` and adapt the verbs.

## Install

```sh
cp examples/ssh-gate/gate ~/.local/bin/agent-gate && chmod 755 ~/.local/bin/agent-gate
```

Test it locally the way sshd will call it:

```sh
SSH_ORIGINAL_COMMAND="status" ~/.local/bin/agent-gate      # allowed
SSH_ORIGINAL_COMMAND="echo test" ~/.local/bin/agent-gate   # {"error": "refused", ...}
```

## Restrict a key the agent already uses

Often the agent already has an unrestricted key on your machine. Lock it down without changing how the agent calls you. The gate skips a leading `agent-gate`, so `ssh you@host agent-gate status` works before and after.

1. Back up: `cp -p ~/.ssh/authorized_keys ~/.ssh/authorized_keys.bak-$(date +%Y%m%d)`
2. Find the line by fingerprint, not by comment: `ssh-keygen -lf ~/.ssh/authorized_keys` lists them in file order. Compare with the fingerprint of the agent's public key.
3. Put the options in front of **that one line only**:
   ```
   command="/home/you/.local/bin/agent-gate",restrict,from="<agent's tailnet IP>" ssh-ed25519 AAAA... remote-agent
   ```
   - `command=` means this key runs the gate and nothing else, whatever the agent asks for
   - `restrict` turns off terminals and port, agent and X11 forwarding
   - `from=` accepts the key only from that address
4. Check that `ssh-keygen -lf ~/.ssh/authorized_keys` still lists every key, and that no other line changed (`diff` against the backup).
5. From the agent's machine: an allowed verb answers; `echo test` returns `{"error": "refused", ...}` and runs nothing.
6. If the agent is locked out: `cp -p ~/.ssh/authorized_keys.bak-YYYYMMDD ~/.ssh/authorized_keys`.

After this the key can no longer open a shell, copy files (scp, rsync, sftp) or run git over SSH. Ask the agent beforehand whether it used the key for anything besides the gate.
