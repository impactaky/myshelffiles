# Agent links

Herdr の live Codex / Claude agent ごとに PR・issue・文書の URL を残す local plugin。
右 bar で新しい順に一覧し、選択した URL を **OSC 52 で手元の clipboard にコピー**する。
Linux の Herdr 0.9.5、Bash、Python 3 標準ライブラリ（curses を含む）が必要。
自動検出と手動追加、global instructions のインストールは含まない。

## 登録とキー設定（検収後に実行）

repository の root で次を実行する。link は絶対 path を受け取る。

```bash
herdr plugin link "$PWD/config/herdr/plugins/local/agent-links" --enabled
```

Herdr の `config.toml` に任意の空いているキーを割り当てる例:

```toml
[[keys.command]]
key = "prefix+l"
type = "plugin_action"
command = "agent-links.toggle"
description = "Toggle agent links"
```

agent pane でキーを押すと右 split が開き、もう一度押すと同じ tab の bar が閉じる。
一覧は約 1 秒ごとに更新される。別 agent の pane に focus を移すとその一覧へ切り替わる。
bar 自身や agent のいない pane に移ったときは直前の agent を表示する。
`j/k`・上下矢印で移動、`Enter` でコピーして agent に focus を戻す、`d` で削除、`q` で閉じる。
削除は再び開いても反映される。URL がなければ「まだありません」と表示する。

## Agent から登録

継承した Herdr 環境で helper を呼ぶ。path は checkout の実際の絶対 path に置き換える。

```bash
/absolute/path/to/agent-links/add-link 'https://example.org/pull/42' 'PR #42'
```

名前を省略すると URL（先頭 256 文字）を表示名にする。同じ URL は名前と登録時刻を更新し先頭へ移動する。
http(s) 以外は拒否する。失敗時は stderr 一行・非 0 終了となる。
Agent の本来の作業は続けること。[短い Agent 向け指示](link-instructions.md) を必要に応じて参照する。
この plugin は Claude / Codex の設定や指示を変更しない。

## 呼び出し元と保存先

登録は `HERDR_ENV=1`、継承した `HERDR_PANE_ID`、絶対 path の `HERDR_SOCKET_PATH` を必須とする。
UI の focus から登録先を選ばない。応答の pane ID、現在の agent kind、`agent_session` の
source / agent / kind / value を検査し、Codex / Claude の `id` のみ認める。
`CODEX_THREAD_ID` があれば会話 ID との一致も検査する。

保存先は `${XDG_STATE_HOME:-$HOME/.local/state}/herdr-agent-links/`。
socket・pane・session の 4 fields に加え、Linux の boot ID・agent PID・`/proc` の開始時刻を
hash に含める。会話 ID だけでは同じ会話の resume を区別できないため、この process binding が必要。
Herdr の `pane process-info` にある Codex / Claude の live process を確認できなければ登録を拒否する。
実プロセスの終了・置換や session の変更後は古い一覧を表示せず、同じ会話の resume に引き継がない。
古い JSON は表示対象から外れるが disk に残るため、不要なら plugin を閉じて保存先を削除できる。
書き込み・削除は file lock 下で JSON を原子的に置換する。pane metadata は使用しない。

## 手元への URL の届け方

インストール済み Herdr 0.9.5 の `herdr api schema --json` を調べた。
`pane.link.activate` / `resolve` は pane の画面座標を対象とし、任意 URL をクライアントの
ブラウザへ送る API はない。plugin の link handler も URL を受け取る側である。
OSC 8 はクリック可能なリンクの表示で、Enter による外部ブラウザ起動の保証はないため採用しない。
Enter は `ESC ] 52 ; c ; <URL の UTF-8 base64> BEL` を出力し、「コピーしました」と知らせる。
Mac のブラウザに貼り付けて開ける。SSH 接続先で `xdg-open` 等は実行しない。

fake Herdr test は OSC 52 の正しい出力までを検査する。実際の clipboard 更新には
Herdr / iTerm2 側の OSC 52 対応と clipboard 書き込み許可が必要で、その完了を plugin から検知する API はない。
実 iTerm2 での転送確認は未実施。検収時は bar で Enter を押し、Mac に URL が貼り付けられることを確認する。

## 検証

repository root から:

```bash
python3 config/herdr/plugins/local/tests/test_plugins.py
python3 config/herdr/plugins/local/tests/test_agent_links.py
shellcheck config/herdr/plugins/local/agent-links/*.sh config/herdr/plugins/local/agent-links/add-link
```

fake Herdr を PATH / HERDR_BIN_PATH に置く host-free test で、状態・表示・選択・コピー・focus・削除・toggle を検査する。
実 Herdr への plugin 登録・本番 config 更新は test では行わない。
