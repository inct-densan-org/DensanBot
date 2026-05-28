# OPERATIONS

## 1. 初期導入

1. Python 3.11+ を準備
2. `uv sync`
3. `.env` 設定
4. `config.json` の確認（テンプレート名、表示名、候補）
5. テンプレート Excel 配置
6. `uv run main.py`

## 2. .env 例

```env
TOKEN=xxxxxxxx
PLAN_NOTICE_CHANNEL_ID=1234567890
REPORT_NOTICE_CHANNEL_ID=1234567890
# 任意: グループ別通知
# AI_CHANNEL_ID=1234567890
```

## 3. Discord 側設定

- Application Commands を許可
- Send Messages / Attach Files / Embed Links 等を付与
- 必要なら MESSAGE CONTENT INTENT を有効化
  - 現構成は Slash 中心のため、実運用で不要なら無効化検討

## 4. 日次・月次・年次運用

- 日次
  - 08:00: 当日予定通知
  - 09:00: カスタムリマインダー通知
  - 活動終了15分前: グループ別通知
  - 20:00: 前日分の未報告リマインド（報告ボタン/活動なしボタン付き）
- 月次
  - `/schedule generate_sheet` で計画書同期
  - `/excel export` で配布
- 年次
  - 4/1 基点処理（年度更新の定期処理）

## 5. 障害対応

- コマンド反映されない
  - `/admin reload` 実行
- 報告導線をチャンネルに常設したい
  - `/report post_guide` を実行して、投稿メッセージをピン留め
- プロセス不調
  - `/admin restart`（start script 必須）
- データ不整合
  - JSON と当月 Excel を突合
  - 必要に応じて `generate_sheet(overwrite=True)` で再生成

## 6. バックアップ

最低限バックアップ対象:
- `config.json`
- `bot_plan_log.json`
- `bot_activity_log.json`
- `regular_plans.json`
- `off_periods.json`
- `reminders.json`
- 月次 Excel 一式

推奨:
- 日次スナップショット + 30日保持
- 月末に提出版 Excel を別フォルダ固定保存

## 7. 引き継ぎ手順

- 運用アカウントのトークン更新手順を文書化
- 通知チャンネルID一覧を別紙管理
- `/config` 変更履歴を残す
- 定期的に `TEST_SCENARIOS.md` を使って回帰確認
