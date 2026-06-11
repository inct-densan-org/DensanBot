# ARCHITECTURE

## 1. 全体構成

- エントリポイント: `main.py`
  - `.env` から `TOKEN` 読込
  - `discord.Intents.all()` で Bot 初期化
  - `cogs/*.py` 自動ロード（`ui_components.py`, `utils.py` を除外）
  - 起動時 `tree.sync()`
- 機能は Cog 分割
  - `plan`, `report`, `history_viewer`, `schedule_manager`, `custom_reminders`, `excel_handler`, `config_manager`, `admin`
- 共通ロジック
  - `cogs/utils.py`: JSON保存、日付・時刻解析、月次生成
  - `cogs/ui_components.py`: View/Modal/Select コンポーネント

## 2. ファイル責務

- `main.py`: Bot ライフサイクル管理
- `cogs/utils.py`:
  - `parse_time`, `parse_date`
  - `load_json`, `save_json`
  - `get_excel_filename_for_month`
  - `generate_monthly_schedule`
- `cogs/plan.py`:
  - `/plan add`, `/plan list`
  - `PlanModal`, `PlanDetailView`
- `cogs/report.py`:
  - `/report open`, `/report post_guide`
  - 活動報告モーダル、通知送信
- `cogs/history_viewer.py`:
  - `/history report`, `/history unreported`
  - 削除/活動なし登録
- `cogs/schedule_manager.py`:
  - `/schedule` 系
  - 8:00 通知、15分前通知、20:00 未報告通知、年度始め処理
- `cogs/custom_reminders.py`:
  - `/remind` 系
  - 毎日9:00の定期通知
- `cogs/excel_handler.py`:
  - `/excel export`
- `cogs/config_manager.py`:
  - `/config` 系、`config.json` 管理
- `cogs/admin.py`:
  - `/admin reload`, `/admin restart`

## 3. データモデル（JSON）

- `bot_plan_log.json`
  - キー: `YYYY-MM-DD`
  - 値: `groups` 辞書（グループ名 -> `start_time`, `end_time`, `location`, `plan_details`, `is_regular`, `id`）
- `bot_activity_log.json`
  - キー: `YYYY-MM-DD`
  - 値: `groups` 辞書（グループ名 -> `start_time`, `end_time`, `location`, `participants`, `description`, `reporter`）
- `regular_plans.json`
  - 定期活動ルール（weekday, group, time, location）
- `off_periods.json`
  - 休止期間（開始/終了、テスト期間フラグ）
- `reminders.json`
  - カスタム通知設定（repeat: none/weekly/monthly/yearly）

## 4. Excel 同期

- 月次生成は `generate_monthly_schedule(year, month, overwrite)` が中核
- 出力先シート: `活動計画書`
- `J9` に年、`J10` に月、`H5` に顧問、`F5` に代表者
- 日別行（`day + 6`）に C/E/F/G を反映
  - C: 開始時刻
  - E: 終了時刻
  - F: 場所（グループ併記）
  - G: 内容（グループ併記）

## 5. コマンド一覧（実装単位）

- Plan: `/plan add`, `/plan list`
- Report: `/report open`, `/report post_guide`
- History: `/history report`, `/history unreported`
- Schedule:
  - `/schedule generate_sheet`
  - `/schedule send_reminder`
  - `/schedule regular add/list`
  - `/schedule off-period add/list`
- Reminder: `/remind add/edit/list`
- Excel: `/excel export`
- Config:
  - `/config show`
  - `/config set advisor`
  - `/config set student_rep`
  - `/config group add/remove`
  - `/config location add/remove`
- Admin: `/admin reload`, `/admin restart`

## 6. 処理フロー（要約）

1. 運用者が `/plan add` で計画登録
2. `/schedule generate_sheet` または定期処理で当月ファイル生成
3. 活動当日に `/report open` またはガイド投稿メッセージのボタンから実績入力
4. `/history` で監査・補正
5. `/excel export` で提出用ファイル出力

## 7. 報告 UI 設計

Discord の Modal は入力コンポーネントが最大5個までのため、活動報告ではグループ/場所をチャット上の Select またはコマンド引数で先に確定し、Modal には日付・時間・人数・内容の4項目だけを載せる。

- リマインドメッセージが対象日・グループを持つ場合は、ボタン押下時に対象活動を自動取得し、場所と予定時間を補完して Modal を直接開く。
- 場所で「その他」を選んだ場合のみ、5項目の `ReportTargetModal`（場所・日付・時間・人数・内容）で自由入力を受ける。グループで「その他」を選んだ場合は処理上のグループ名は「その他」のままにし、ユーザーにはグループ名ではなく活動内容を入力してもらう。
- これにより、通常ケースは4項目、例外ケースでも5項目に収まり、Discord API の制限を避けつつ入力負担を抑える。
- 報告または活動なし登録が完了した場合、`REPORT_NOTICE_CHANNEL_ID` へ報告通知を送信し、起点になったリマインド/ガイドメッセージの Embed にも報告済みステータスを追記する。

## 8. 既知課題・潜在バグ（確認結果）

- 修正済み: `generate_monthly_schedule` で時刻欠損データしかない日付に対し `min()/max()` が例外になる問題。
  - 欠損時は `None` を書き込むフォールバックへ変更。
- `history_viewer.py` で報告削除・活動なし登録時、Excel 側の再書き込みは自動実行されない。
- `admin.py` の reload 除外リストが `main.py` と不一致だった（`schedule.py`）。今回一致させた。
- `/admin restart` 実行には `start.bat` / `start.sh` が必要（リポジトリに同梱されていない場合は運用側で用意）。
- JSON ファイルはロックなし読み書きのため、同時実行時の競合余地あり。

## 9. 改善候補

- JSON I/O にファイルロック導入
- 履歴補正時の Excel 即時再同期
- Intents の最小権限化
- SharePoint 連携を非個人依存で実装（`docs/ROADMAP.md`）
