# 今の agent に関係する URL を開く

- 誰が: 開発者
- 目的: 見ている agent が作った PR や参照した URL を、探し直さずに手元のブラウザで開く
- 始まり: 開発者が agent の pane で右 bar を開くキーを押す

## 基本シナリオ

1. 開発者が agent の pane で右 bar を開くキーを押す。
2. システムが pane の右に bar を開き、その agent instance に結び付いた URL を新しい順に並べる。
3. 開発者が URL を一つ選んで開く。
4. システムが手元（Mac）のブラウザでその URL を開き、focus を agent の pane に戻す。

## extension

- **URL がまだない**: 手順 2 で分かれ、bar が「まだありません」と表示する。目的に届かない。
- **別の agent に移る**: 手順 2 の後に開発者が別の agent の pane へ移ると、bar がその agent の URL に切り替わる。手順 3 へ戻る。目的に届く。
- **URL を消す**: 手順 3 で分かれ、開発者が要らない URL を消す。その agent の一覧から消え、手順 3 へ戻る。目的に届く。
- **URL を手で足す**: 手順 3 で分かれ、開発者が URL を貼って足す。手順 3 へ戻る。目的に届く（優先は低い）。
- **ブラウザで開けない**: 手順 4 で分かれ、システムが URL を手元の clipboard にコピーして知らせる。目的に届く。
- **agent が終了した**: agent instance が終わると、その URL の一覧も消える。

## 出力の例

右 bar のイメージ（幅・記号・キーは例）。

```
 agent pane                         │ links: claude · 公開タイトル
                                    │ ▸ PR #42  Add link bar
                                    │   github.com/example/repository/pull/42
                                    │   Issue #40  bar の要望
                                    │   herdr.dev/llms.txt
                                    │
                                    │ Enter 開く  d 消す  a 足す  q 閉じる
```

## 制約

- 事前条件: 右 bar の plugin が登録済みで、pane に Herdr が識別した agent がいる。
- 事後条件: 開いた URL は一覧に残る。消した URL だけが消える。
- 未確認の前提: Herdr が https の OSC 8 link を外の iTerm2 に渡せるか。渡せないときは clipboard コピーを基本にする。
- 合意: 一覧は agent instance と 1 対 1。消すのは要る、足すは低優先。agent 終了で一覧を消し、resume しても引き継がない。開けないときは clipboard へコピー。新しい順に並べる（すべて 2026-10-25）。

## test case

`config/herdr/plugins/local/tests/test_agent_links.py` で実行する。今回の実装では手動追加は対象外、開く操作は OSC 52 コピーによる fallback とする。

| 通るシナリオ | 確かめること | 実行するもの |
|---|---|---|
| 基本シナリオ | URL が 2 件ある agent で bar を開くと 2 件が新しい順に出て、選ぶと手元のブラウザでその URL が開く | `test_selection_copy_exact_bytes_notice_focus_and_delete_persist`（OSC 52）。Mac の転送は手動検収 |
| URL がまだない | URL が 0 件の agent で bar を開くと「まだありません」と出る | `test_empty_focus_switch_and_non_agent_focus` |
| 別の agent に移る | agent A で bar を開いたまま agent B の pane へ移ると、B の URL だけが出る | `test_empty_focus_switch_and_non_agent_focus` |
| URL を消す | 2 件のうち 1 件を消すと、bar を開き直しても 1 件だけが出る | `test_selection_copy_exact_bytes_notice_focus_and_delete_persist` |

## 扱わないもの

- 別の agent の URL をまとめて探すこと: 対象外と合意（2026-10-25）。
- ブラウザ以外での中身の表示（PR の状態や CI の結果を bar に出す）: この task の目的は「すぐ開く」まで。
