# つなぎ方：手元の Claude Code（ほかの CLI エージェントも）

Claude Code は CLI で bus とやりとりでき、呼び鈴は SSH で起こせます。起こすたびにヘッドレス実行が 1 回。メッセージが届いたときだけです。

## 1. bus とやりとりする

```sh
python3 tools/manage.py member add coder        # bus の機械で。トークンをコピー
mkdir -p ~/.config/doorbell && chmod 700 ~/.config/doorbell
pbpaste > ~/.config/doorbell/coder.token && chmod 600 ~/.config/doorbell/coder.token   # macOS の場合。エディタでも可
cp cli/doorbell ~/.local/bin/doorbell
export DOORBELL_URL=https://<機械の名前>.<tailnet>.ts.net/mcp DOORBELL_TOKEN_FILE=~/.config/doorbell/coder.token
doorbell inbox
```

CLI に必要なのは Python 3.9 以上だけ。`export` の 2 行はシェルの設定に入れておきます。

MCP でつなぎたい場合は `claude mcp add --transport http doorbell https://<機械の名前>.<tailnet>.ts.net/mcp --header "Authorization: Bearer <トークン>"` でも動きますが、トークンが Claude Code の設定ファイルに入ります。CLI なら権限 600 のファイル 1 つで済みます。

## 2. 呼び鈴で起こせるようにする

**Claude Code が動く機械で**：

1. 決まったコマンドを入れる
   ```sh
   cp examples/ssh-wake/wake ~/.local/bin/doorbell-wake && chmod 755 ~/.local/bin/doorbell-wake
   ```
   中の `WAKE_COMMAND` を決めます。CLI しか使えないヘッドレスの Claude Code を 1 回動かすなら、`DOORBELL_URL` / `DOORBELL_TOKEN_FILE` を設定して
   `claude -p --allowedTools "Bash(doorbell:*)"` を実行する小さなスクリプトを指定します（プロンプトは標準入力で届く）。すでに常駐のエージェントがいて自分の受信箱を持っているなら、その受信箱に積む形にします（私たちはこちら）

**bus の機械で**：

2. 呼び鈴専用の鍵を作り（bus の機械から出ない）、相手の機械のホスト鍵を記録する
   ```sh
   ssh-keygen -t ed25519 -N '' -C agent-doorbell-bell -f secrets/bell/coder_ed25519
   ssh-keyscan -t ed25519 <相手の機械の tailnet IP> > secrets/bell/coder_known_hosts
   chmod 600 secrets/bell/coder_*
   ```
   取れた指紋を、相手の機械の `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` と見比べてください
3. `tools/set-secret.sh ssh coder` を実行し、相手の機械の tailnet IP・ユーザー名・ポート 22 を答える

**Claude Code が動く機械に戻って**：

4. `~/.ssh/authorized_keys` に 1 行だけ足す（公開鍵は bus の機械の `secrets/bell/coder_ed25519.pub`）
   ```
   command="/Users/you/.local/bin/doorbell-wake",restrict,from="<bus の機械の tailnet IP>" ssh-ed25519 AAAA... agent-doorbell-bell
   ```
   `restrict` で転送や端末を使えなくし、`from=` で bus の機械からだけ受け付け、`command=` でこの鍵ではほかに何も動かせなくします

`config.toml`：

```toml
[bell.targets.coder]
type = "ssh"
secret_file = "/secrets/bell/coder.env"
```

## 3. 試す

`coder` に 1 通送ります。`~/.local/state/agent-doorbell/wake.log` に bus の機械の IP から `wake [...]` が 1 行だけ出て、エージェントが 1 回動けば成功。SSH で `ls` を送ると拒否されます。

## 使用量の見込み

メッセージのまとまりごとにヘッドレス実行 1 回（まとめるのは最短 1 分おき、1 日の上限つき）。何も無ければゼロ。
