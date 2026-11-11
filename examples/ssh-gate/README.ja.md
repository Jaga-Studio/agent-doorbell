# SSH ゲートの型

[English](README.md)

`gate` は見本で、bus の一部ではありません。離れた場所のエージェントに、手元の機械で決まったことだけ（状態を読む、メモを置く）をさせたいが、シェルは渡したくないときに使います。動詞は `gate` 先頭の説明を見て自分用に直してください。

## 入れる

```sh
cp examples/ssh-gate/gate ~/.local/bin/agent-gate && chmod 755 ~/.local/bin/agent-gate
```

sshd と同じ渡し方で、手元で試せます。

```sh
SSH_ORIGINAL_COMMAND="status" ~/.local/bin/agent-gate      # 通る
SSH_ORIGINAL_COMMAND="echo test" ~/.local/bin/agent-gate   # {"error": "refused", ...}
```

## エージェントがすでに使っている鍵を絞る

エージェントが、何でもできる鍵をすでに持っていることはよくあります。呼び方を変えさせずに絞れます。gate は先頭の `agent-gate` を読み飛ばすので、`ssh you@host agent-gate status` は絞る前も後も同じように動きます。

1. バックアップ：`cp -p ~/.ssh/authorized_keys ~/.ssh/authorized_keys.bak-$(date +%Y%m%d)`
2. 対象の行は、コメントではなく指紋で探す：`ssh-keygen -lf ~/.ssh/authorized_keys` がファイルの順に一覧を出すので、エージェントの公開鍵の指紋と見比べる
3. **その 1 行だけ** の先頭にオプションを付ける
   ```
   command="/home/you/.local/bin/agent-gate",restrict,from="<エージェントの tailnet IP>" ssh-ed25519 AAAA... remote-agent
   ```
   - `command=`：何を頼まれても、この鍵では gate しか動かない
   - `restrict`：端末・ポート転送・エージェント転送・X11 転送を止める
   - `from=`：そのアドレスからしか受け付けない
4. `ssh-keygen -lf ~/.ssh/authorized_keys` で全部の鍵がまだ読めること、ほかの行が変わっていないこと（バックアップと `diff`）を確かめる
5. エージェントの機械から：許可した動詞は答えが返り、`echo test` は `{"error": "refused", ...}` が返って何も実行されない
6. 締め出してしまったら：`cp -p ~/.ssh/authorized_keys.bak-YYYYMMDD ~/.ssh/authorized_keys`

絞ったあとは、この鍵でシェルを開くことも、ファイルのコピー（scp・rsync・sftp）も、SSH 経由の git もできなくなります。gate 以外にこの鍵を使っていないか、先にエージェントに聞いておいてください。
