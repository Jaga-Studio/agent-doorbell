#!/bin/bash
# Write a bell secret file (secrets/bell/<member>.env, chmod 600) without the value ever
# appearing on screen, in shell history, in process arguments, or in an AI chat.
# Run it in your own terminal, not through an AI agent.
#
#   tools/set-secret.sh webhook <member> [ssh-host]   URL + optional key (macOS: from the clipboard)
#   tools/set-secret.sh ssh <member> [ssh-host]       SSH_HOST/SSH_USER/... for an ssh wake-up
#
# With [ssh-host], the file is written on that host under $DOORBELL_DIR (default ~/agent-doorbell on that host).
set -eu
kind="${1:-}"; member="${2:-}"; remote="${3:-}"
case "$kind" in webhook|ssh) ;; *) sed -n '2,10p' "$0"; exit 1;; esac
[[ "$member" =~ ^[A-Za-z0-9_-]+$ ]] || { echo "member name: letters, digits, - and _"; exit 1; }
# default: the checkout you are in, or ~/agent-doorbell on the remote host (relative = from its home)
dir="${DOORBELL_DIR:-$( [[ -n "$remote" ]] && echo agent-doorbell || pwd)}/secrets/bell"

grab() {  # $1 = prompt; prints the value
  if command -v pbpaste >/dev/null; then
    echo "$1 Copy it, then press Enter." >&2; read -r _; pbpaste | tr -d '\r\n'
  else
    echo "$1 Paste it and press Enter (hidden)." >&2; read -rs v; echo >&2; printf '%s' "$v"
  fi
}

if [[ "$kind" == webhook ]]; then
  url="$(grab "1/2 Webhook URL.")"
  [[ "$url" =~ ^https://[^[:space:]]+$ ]] || { echo "Not an https:// URL. Nothing saved."; exit 1; }
  key="$(grab "2/2 Key (an 'Authorization: Bearer ...' line is fine). No key: copy nothing / leave empty.")"
  key="${key#Authorization: Bearer }"; key="${key#Authorization:Bearer }"; key="${key#Bearer }"
  [[ "$key" == "$url" ]] && key=""
  [[ "$key" =~ [[:space:]] ]] && { echo "The key contains spaces. Nothing saved."; exit 1; }
  echo "Header for the key: press Enter for 'Authorization: Bearer', or type a header NAME only (e.g. X-Webhook-Secret):" >&2
  read -rs header; echo >&2
  case "$header" in Authorization*|authorization*|Bearer*) header="";; esac
  [[ -z "$header" || "$header" =~ ^[A-Za-z0-9-]+$ ]] || { echo "Bad header name."; exit 1; }
  content="URL=$url"$'\n'
  [[ -n "$key" ]] && content+="KEY=$key"$'\n'
  [[ -n "$header" ]] && content+="KEY_HEADER=$header"$'\n'
else
  read -rp "Host the bell connects to (IP or name): " h
  read -rp "User on that host: " u
  read -rp "Port [22]: " p
  content="SSH_HOST=$h"$'\n'"SSH_USER=$u"$'\n'"SSH_PORT=${p:-22}"$'\n'"SSH_KEY=secrets/bell/${member}_ed25519"$'\n'"SSH_KNOWN_HOSTS=secrets/bell/${member}_known_hosts"$'\n'
fi

write='umask 077; mkdir -p "$1" && chmod 700 "$1" && cat > "$1/$2.env.tmp" && mv "$1/$2.env.tmp" "$1/$2.env"'
if [[ -n "$remote" ]]; then
  printf '%s' "$content" | ssh "$remote" "sh -c '$write' _ '$dir' '$member'"
else
  printf '%s' "$content" | sh -c "$write" _ "$dir" "$member"
fi
unset url key content
command -v pbcopy >/dev/null && printf '' | pbcopy
echo "Saved ${dir}/${member}.env (chmod 600). The bell picks it up within a few seconds."
