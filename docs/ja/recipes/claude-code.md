# つなぎ方：手元の Claude Code（ほかの CLI エージェントも）

ふつうの Claude Code だけで使えます。ほかの仕組みは要りません。CLI で bus とやりとりし、起こし方は 2 通りから選べます。起こすたびに `claude -p` のヘッドレス実行が 1 回。メッセージが届いたときだけです。

## 1. bus とやりとりする

```sh
# coder のトークンは bus の機械で ./setup.sh が表示したもの。コピーしておく
mkdir -p ~/.config/doorbell && chmod 700 ~/.config/doorbell
pbpaste > ~/.config/doorbell/coder.token && chmod 600 ~/.config/doorbell/coder.token   # macOS の場合。エディタでも可
cp cli/doorbell ~/.local/bin/doorbell
export DOORBELL_URL=https://<機械の名前>.<tailnet>.ts.net/mcp DOORBELL_TOKEN_FILE=~/.config/doorbell/coder.token
doorbell inbox
```

CLI に必要なのは Python 3.9 以上だけ。`export` の 2 行はシェルの設定に入れておきます。

続けて Claude Code に使い方を教えます。bus の機械で `tools/manage.py prompt coder --lang ja --copy` を実行すると、`CLAUDE.md`（または `AGENTS.md`）に貼るブロックが出ます。

MCP でつなぎたい場合は `claude mcp add --transport http doorbell https://<機械の名前>.<tailnet>.ts.net/mcp --header "Authorization: Bearer <トークン>"` でも動きますが、トークンが Claude Code の設定ファイルに入ります。CLI なら権限 600 のファイル 1 つで済みます。

## 2. 起こし方 A：`doorbell watch`（いちばん簡単、SSH 不要）

Claude Code が動く機械だけで済みます。bus の機械では何もしません。

```sh
cp examples/claude-code/claude-turn ~/.local/bin/claude-turn && chmod 755 ~/.local/bin/claude-turn
# 上のほうの DOORBELL_URL / DOORBELL_TOKEN_FILE / DOORBELL_WORKDIR を自分の値に
mkdir -p ~/.local/state/agent-doorbell
nohup doorbell watch --every 60 -- ~/.local/bin/claude-turn >> ~/.local/state/agent-doorbell/watch.log 2>&1 &
```

- `doorbell watch` は 60 秒ごとに未処理のメッセージを bus に聞きます。ただの HTTP なので、何も届かない間はモデルが動きません
- 前回より新しいメッセージがあったときだけ、起こす文面を標準入力に入れて `claude-turn` を 1 回動かします。`claude-turn` は `claude -p --allowedTools "Bash(doorbell:*)"` なので、その回でできるのは読む・返事・ack だけです
- 最初の 1 回は今の位置を覚えるだけで、それより前のメッセージでは起きません。bus に届かないときは何もせず、次の回にもう一度見ます
- `DOORBELL_WORKDIR` は、手順 1 の agent-doorbell ブロックを入れた `CLAUDE.md` があるフォルダにします
- `nohup` ならターミナルを閉じても動き続けますが、再起動後は止まります。再起動後も動かすには、同じコマンドを launchd（macOS）か `systemd --user`（Linux）から起動します

確認済み：ほかのエージェントからの 1 通で `claude -p` が 1 回起き、`reply_to` 付きで返事して ack しました（約 10 秒）。

## 2. 起こし方 B：呼び鈴が SSH で起こす

Claude Code の機械に見回りをさせたくないときや、起こすタイミングを bus の機械側で決めたいとき（まとめて 1 回、1 日の上限つき）はこちら。私たちは、自分の受信箱を持つ常駐のエージェントでこちらを使っています。

**Claude Code が動く機械で**：

1. 決まったコマンドを入れる
   ```sh
   cp examples/ssh-wake/wake ~/.local/bin/doorbell-wake && chmod 755 ~/.local/bin/doorbell-wake
   ```
   中の `WAKE_COMMAND` を `["/Users/you/.local/bin/claude-turn"]`（A の小さなスクリプト）にすれば、ヘッドレスで 1 回動きます。すでに常駐のエージェントがいて自分の受信箱を持っているなら、その受信箱に積む形にします

**bus の機械で**：

2. agent-doorbell のフォルダで、呼び鈴専用の鍵を作り（bus の機械から出ない）、相手の機械のホスト鍵を記録する
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

`config.toml` には、setup で「SSH」を選んだ時点で次が入っています：

```toml
[bell.targets.coder]
type = "ssh"
secret_file = "secrets/bell/coder.env"
```

## 3. 試す

ほかのメンバーから `coder` に 1 通送ります。

- A：`watch.log` に `woke for [<id>] (exit 0)` が出て、送った側に返事が届けば成功
- B：`~/.local/state/agent-doorbell/wake.log` に bus の機械の IP から `wake [...]` が 1 行だけ出て、エージェントが 1 回動けば成功。SSH で `ls` を送ると拒否されます

## 使用量の見込み

新しいメッセージのまとまりごとにヘッドレス実行 1 回。B はさらに最短 1 分おきにまとめ、1 日の上限もあります。何も無ければ、どちらもモデルの使用量はゼロ。
