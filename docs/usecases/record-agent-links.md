# 作業に関係する URL を残す

- 誰が: 会話中の Agent（Claude Code / Codex）
- 目的: 自分が作った PR や作業の鍵になる URL を自分の会話に結び付け、開発者が後で右 bar からすぐ開けるようにする
- 始まり: Agent が PR を作るなど、残す価値のある URL を得る

## 基本シナリオ

1. Agent が PR を作り、その URL を得る。
2. Agent が URL と短い名前（例: `PR #42 Add link bar`）を登録する。
3. システムが呼び出し元の会話を確かめ、その一覧に URL を加える。
4. システムが、開いている右 bar の表示を更新する。

## extension

- **自動検出**: 手順 2 の代わりに、Agent のツール実行の結果に URL が出たことをシステムが検出し、その会話に加える。検出元は gh に限らない。手順 4 へ戻る。目的に届く。
- **同じ URL をもう一度**: 手順 3 で分かれ、既にある URL は増やさず、名前と時刻だけを新しくする。目的に届く。
- **呼び出し元を確かめられない**: 手順 3 で分かれ、Herdr の外や agent が識別されていない pane からの登録を拒否する。Agent の本来の作業は止めない。目的に届かない。
- **URL ではない**: 手順 3 で分かれ、http(s) 以外を拒否する。目的に届かない。

## 出力の例

登録の後の右 bar（例）。自動検出したものは名前の代わりにホストとパスを出す。

```
links: claude · 公開タイトル
▸ PR #42  Add link bar                (Agent が登録)
  github.com/example/repository/issues/40   (自動検出)
```

## 制約

- 事前条件: Agent が Herdr の pane で動いていて、Herdr が agent の会話を識別している。
- 事後条件: URL はその会話の一覧にだけ入る。別の agent の一覧は変わらない。
- 未確認の前提: Claude Code と Codex の両方で、ツール実行後に URL を拾える hook がある。
- 合意: 一覧は agent の会話（session）と 1 対 1。Agent の自律登録と自動検出の両方で加える（2026-10-25）。
- 合意: 自動検出はツール実行結果から拾い、範囲と上限は order で決める。登録の失敗は黙って終わり、作業を止めない（`set_title.py` と同じ方針）（2026-10-25）。

## test case

`config/herdr/plugins/local/tests/test_agent_links.py` で実行する。今回の実装では自動検出は対象外。CLI は失敗時に非 0 終了し、呼び出す Agent が本来の作業を続ける。

| 通るシナリオ | 確かめること | 実行するもの |
|---|---|---|
| 基本シナリオ | pane の Agent が URL と名前を登録すると、その agent の一覧に 1 件増え、別の agent の一覧は変わらない | `test_register_isolated_order_duplicate_and_timestamp` |
| 自動検出 | Agent のツール結果に `https://github.com/.../pull/42` が出ると、その agent の一覧に入る | 今回は対象外 |
| 同じ URL をもう一度 | 同じ URL を 2 回登録しても 1 件のまま、名前が新しいものになる | `test_register_isolated_order_duplicate_and_timestamp` |
| 呼び出し元を確かめられない | `HERDR_ENV` のない環境から登録すると拒否され、どの一覧も変わらず、Agent の作業を止めない | `test_rejections_leave_all_lists_unchanged`（拒否・非 0 終了）、作業継続は Agent 向け指示 |

## 扱わないもの

- 画面の出力全体から URL を拾うこと: ノイズが多く、ツール結果に絞る（2026-10-25 合意）。
- fork した会話や新規会話への引き継ぎ: 一覧は会話と 1 対 1 のため。
