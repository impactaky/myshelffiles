# Agent の関連 URL 登録

Herdr 内で PR を作ったとき、または作業の鍵になる issue・文書を参照したとき、
その URL と短い名前をこの directory の `add-link` で登録する。

```bash
/absolute/path/to/agent-links/add-link 'https://example.org/pull/42' 'PR #42'
```

継承した `HERDR_ENV` / `HERDR_PANE_ID` / `HERDR_SOCKET_PATH` をそのまま使う。
他 pane や focus から登録先を選ばず、環境変数を推測して作らない。
http(s) のみ。名前を省略すると URL が表示名になる。同じ URL は名前と時刻を更新する。
登録に失敗しても、本来の作業を止めたり登録のための権限拡大・別 session 探索をしたりせず続ける。
