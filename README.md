# DensanBot

Discord 上で「活動計画」と「活動報告」を入力し、学校提出向け Excel 帳票（活動計画書・活動報告書）を自動更新する部活動運用 Bot です。

> このリポジトリは **Python 3.11+ / discord.py** を前提にしています。帳票更新ロジックは `openpyxl` を用いて実装されています。

## 概要

- スラッシュコマンド中心で、計画・報告・履歴・リマインダー・設定変更を Discord 上で完結
- JSON（運用データ）と Excel（提出物）を同期
- 定期活動・休止期間をルール化して月次計画を半自動生成
- 日次通知（8:00）・活動終了前通知（15分前）・カスタム通知（9:00）を自動実行
- 未報告リマインド（20:00）で「計画あり・報告なし」を通知し、ボタンから報告/活動なし登録が可能

詳細設計は以下を参照してください。

- `docs/ARCHITECTURE.md`
- `docs/OPERATIONS.md`
- `docs/ROADMAP.md`

---

## クイックスタート

1. 依存関係をインストール

```bash
uv sync
```

2. `.env` を作成（最低限 `TOKEN`, `PLAN_NOTICE_CHANNEL_ID`, `REPORT_NOTICE_CHANNEL_ID`）
3. Excel テンプレートを配置（`config.json` の `template_file_name`）
4. 起動

```bash
uv run main.py
```

---

## 主要コマンド一覧（運用者向け）

- `/plan add`, `/plan list`: 活動計画の登録・編集・削除
- `/report open`: 活動報告入力（予定外活動や過去日入力にも対応）
- `/report post_guide`: 当該チャンネルに使い方ガイドと報告ボタンを投稿（ピン留め推奨）
- `/history report`, `/history unreported`: 報告履歴の確認・削除 / 未報告計画の処理
- `/schedule generate_sheet`: 月次計画書生成（定期活動・休止期間を反映）
- `/schedule regular add/list`: 定期活動ルール管理
- `/schedule off-period add/list`: 休止期間ルール管理
- `/remind add/edit/list`: カスタムリマインダー管理
- `/excel export`: 月次 Excel の出力（zip/xlsx）
- `/config ...`: 顧問名・代表者名・選択肢管理
- `/admin reload`, `/admin restart`: Cog 再読込・再起動

全コマンド仕様は `docs/ARCHITECTURE.md` を参照。

---

## リポジトリ構成

- `main.py`: Bot起動、Cog自動ロード、`tree.sync()`
- `cogs/`: 機能別Cog（計画・報告・履歴・スケジュール・Excel・設定・管理）
- `cogs/ui_components.py`: View / Modal / Select など UI 部品
- `cogs/utils.py`: JSON I/O、日付/時刻パース、月次生成など共通ロジック
- `docs/`: 設計・運用・将来計画ドキュメント
- `TEST_SCENARIOS.md`: 手動検証シナリオ

---

## 運用上の注意（重要）

- `*.json` と `*.xlsx` は `.gitignore` 対象ですが、**実行で生成される運用データ**です。誤削除防止のため定期バックアップ運用を推奨。
- `config.json` は運用設定（テンプレート、表示名、候補リスト）を保持するため、環境別に管理方針（Git管理するか）を統一してください。
- `/config` でグループ/場所を変更した場合、Discord 側の choices 反映には `/admin reload` または再起動が必要。
- `/admin restart` は `start.bat` または `start.sh` が実行可能であることを前提にしています。

---

## 既知課題（2026-05時点）

- 履歴画面で報告削除・「活動なし」登録した際に、JSON は更新されるが Excel 側に即時反映されないケースがある。
- JSON を複数 Cog が直接読み書きするため、同時操作時の競合対策（ロック/トランザクション）がない。
- `discord.Intents.all()` は現状の Slash 中心運用に対して広め。最小権限化の余地あり。

追加提案・移行判断・SharePoint 連携案は `docs/ROADMAP.md` に整理しています。
