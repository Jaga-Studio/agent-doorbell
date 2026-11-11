# Security

## What agent-doorbell protects against

- **Strangers on the internet.** The bus is meant to be reachable only on your private network (tailnet). It refuses to bind to anything but `127.0.0.1` or a `100.x` tailnet address unless you override it, and it rejects unknown `Host` headers (DNS-rebinding protection).
- **A leaked token.** Tokens are per agent and stored only as SHA-256 hashes. `tools/manage.py member rotate <name>` replaces one without touching the others.
- **A compromised bell.** The bell has no port, reads the database read-only, and its SSH key can only run `wake <ids>` from the bus host's address.
- **Secrets in logs and chats.** Webhook URLs, keys and hosts are never logged. `tools/set-secret.sh` writes secrets from the clipboard without printing them.

## What it does not protect against

- **Prompt injection between agents.** Any member can send any text to the members it may write to. Treat every message as untrusted input from a peer. The protocol ([docs/protocol.md](docs/protocol.md)) tells agents never to act on money, sending, deleting or publishing without their human's confirmation; put that rule in every agent's instructions, and use `can_send_to` to limit who can reach whom.
- **A compromised member.** A member's token can read that member's inbox and send as that member.
- **Message confidentiality at rest.** Messages are stored in plain SQLite on the bus host. Do not put secrets in messages; acked messages are deleted after `acked_retention_days`.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting on this repository instead of a public issue.
