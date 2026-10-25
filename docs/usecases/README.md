# ユースケース

Herdr の agent ごとの関連 URL の quick access を、誰が何のために使えるかの一覧。Herdr の local plugin で扱うものを書く。

## 利用者

| 利用者 | 説明 |
|---|---|
| 開発者 | Herdr を iTerm2 から ssh 越しに使い、複数の agent を見て回る人 |
| 会話中の Agent | pane の中の Claude Code / Codex。自分が作った PR や参照した URL を知っている |

## ユースケース

上にあるものほど優先する。状態はここだけに書く。

| ユースケース | 誰が | 目的 | 状態 | 受け入れ検査書 |
|---|---|---|---|---|
| [今の agent に関係する URL を開く](open-agent-links.md) | 開発者 | 右の bar で、見ている agent の PR などを一覧し、すぐ手元のブラウザで開く | Basic Scenario Enabled | |
| [作業に関係する URL を残す](record-agent-links.md) | 会話中の Agent | PR を作ったり重要な URL を参照したりしたとき、自分の agent に結び付けて開発者が後で開けるようにする | Basic Scenario Enabled | |
| 会話の URL を手で直す | 開発者 | 足す・消すを独立に行う | 対象外: 消す・足すは「URL を開く」の extension に含める（2026-10-25） | |
| 会話をまたいで URL を探す | 開発者 | PR から元の agent に戻る | 対象外: 不要（2026-10-25） | |

| 状態 | 意味 |
|---|---|
| Goal Established | 目的と価値が決まった |
| Scenario Structure Understood | 基本シナリオと extension の構造が分かった |
| Basic Scenario Enabled | 基本シナリオが最初から最後まで通る |
| Sufficient Scenarios Fulfilled | 使える範囲のシナリオが満たされた |
| All Scenarios Fulfilled | すべてのシナリオが満たされた |

Basic Scenario Enabled から先は、受け入れ検査書で確かめたものだけに付ける。

## 用語と共通の要求

- 用語: Herdr の語彙（workspace, tab, pane, agent, plugin, pane metadata）は `herdr --skill` に従う。**会話** は agent の種類と session ID の組で識別する agent の会話を指す。resume しても同じ会話で、fork や新規会話は別の会話になる。
- 関連文書: [plugin の利用説明](../../config/herdr/plugins/local/agent-links/README.md)、[pane metadata の前例](../../config/herdr-mcp/README.md)

## 合意した前提

- URL の一覧は agent の会話（session）と 1 対 1 に対応する（2026-10-25 合意。当初の「agent instance と 1 対 1」から同日に変更）
- URL は Agent が自律的に加えるか、自動検出で加える。検出元は gh に限らない（2026-10-25 合意）
- 開発者による削除は要る。手で追加するのは残してもよいが優先は低い（2026-10-25 合意）
- resume すると、どの pane・Herdr session でも同じ一覧が出る（2026-10-25 合意）
- 選ぶと手元のブラウザで開き、開けないときは clipboard へコピーする（2026-10-25 合意）
- 自動検出は画面全体ではなく Agent のツール実行結果から拾う。範囲と上限は order で決める（2026-10-25 合意）

## 実装の前提

- 技術スタック: Herdr 0.9.5 の local plugin。置き場は `config/herdr/plugins/local/<plugin名>/`、登録は `herdr plugin link`。右 bar は `[[panes]] placement = "split"` を右へ開く（reviewr / herdr-nvim と同じ作り）。言語は仮定（既存 local plugin に合わせて bash + Python）。
- 依存: Agent からの登録は `set_title.py` と同じく、継承した `HERDR_ENV` / pane ID / `HERDR_SOCKET_PATH` と agent session の識別で自分の会話を特定する（仮定）。自動検出は Claude Code / Codex の hook（ツール実行後）で URL を拾う（仮定）。
- 保存: 会話ごとの JSON を XDG state directory に保存する。ファイル名は agent の種類・kind・session ID の hash。
- 実行環境: Linux の Herdr server に Mac の iTerm2 から ssh で接続。ブラウザは Mac 側。
- 開く手段: Enter は OSC 52 でコピーする。focus の追従は 1 秒ごとの読み取りで行う。実 iTerm2 への転送確認は検収時に行う。

## test case の実行方法

```bash
python3 config/herdr/plugins/local/tests/test_plugins.py
python3 config/herdr/plugins/local/tests/test_agent_links.py
```

fake Herdr に対して登録と bar の状態・操作を検査する。今回の実装は自律登録・一覧・切り替え・削除・OSC 52 コピーを対象とし、自動検出と手動追加は対象外。
