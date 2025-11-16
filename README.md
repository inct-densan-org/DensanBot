# 電算部 活動報告Bot

これは、Discordを通じて部活動の活動計画・報告を管理し、Excelファイルに自動で記録するためのBotです。

## 主な機能

- **活動計画・報告**: `/plan` と `/report` コマンドで、活動の予定と実績を簡単に入力できます。
- **Excel自動生成・更新**: 月初の計画入力時に、テンプレートからその月のExcelファイルを全自動で生成。定期活動や休止期間も反映します。
- **柔軟な入力**: 日付や時刻の入力は、全角・半角の違いを吸収し、`yyyyMMdd` や `hhmm` 形式のショートハンドにも対応しています。
- **高度なリマインダー**:
  - **活動終了リマインダー**: 各グループの活動終了15分前になると、設定されたチャンネルに自動でリマインドメッセージを送信します。
  - **カスタムリマインダー**: 「ドメイン更新」のような繰り返し可能なタスクを登録・管理・通知できます。
- **履歴の閲覧と操作**: Discord上で過去の活動報告を確認したり、間違えた報告を安全に削除したりできます。
- **管理者機能**: Botの設定変更や再起動をDiscordのコマンドから安全に行えます。

---

## 導入と設定

### 1. 必要なライブラリのインストール

このBotを動作させるには、以下のPythonライブラリが必要です。

```sh
uv add discord.py python-dotenv openpyxl python-dateutil
```

### 2. Botの招待

Discord Developer PortalでBotを作成し、以下の権限を付与した招待URLでサーバーに招待してください。

- `チャンネルを見る (View Channel)`
- `メッセージを送信 (Send Messages / Send Messages in Threads)`
- `埋め込みリンク (Embed Links)`
- `ファイルを添付 (Attach Files)`
- `メッセージの管理 (Manage Messages)`
- `メッセージ履歴を読む (Read Message History)`
- `アプリケーションコマンドの使用 (Use Application Commands)`

**【重要】** Botの「Privileged Gateway Intents」設定で、**「SERVER MEMBERS INTENT」**と**「MESSAGE CONTENT INTENT」**の両方を**ON**にしてください。

### 3. 設定ファイルの準備

Botを初めて起動する前に、ルートディレクトリに `.env` ファイルを作成し、以下の内容を記述します。

```env
# BotのDiscordトークン (必須)
TOKEN=YOUR_DISCORD_BOT_TOKEN

# --- 通知チャンネルID (必須) ---
# 「今日の活動予定」や「カスタムリマインダー」を通知するチャンネル
PLAN_NOTICE_CHANNEL_ID=YOUR_GENERAL_NOTICE_CHANNEL_ID
# 活動報告があった際のサイレント通知が投稿されるチャンネル
REPORT_NOTICE_CHANNEL_ID=YOUR_REPORT_LOG_CHANNEL_ID

# --- グループ別リマインダー (任意) ---
# グループごとの活動終了リマインダーを送信したいチャンネル
# グループ名の大文字・記号は `_` に変換して記述 (例: CG･DTM -> CG_DTM_CHANNEL_ID)
# AI_CHANNEL_ID=...
# WEB_CHANNEL_ID=...
```

### 4. テンプレートファイルの準備

ルートディレクトリに、活動報告書のテンプレートとなるExcelファイル（例: `[電子計算機部]R0年xx月_活動計画書・活動報告書・活動延長願（複合書式）.xlsx`）を配置してください。
このファイル名は、後述する `/config` コマンドで変更できます。

### 5. Botの起動

お使いの環境に合わせて、以下のスクリプトを実行してBotを起動します。

- **Windows**: `start.bat` をダブルクリック
- **Linux**: ターミナルで `./start.sh` を実行 (初回のみ `chmod +x start.sh` が必要)

---

## コマンド一覧

### `/plan` - 活動計画の管理

- `/plan add`
  - **説明**: 活動計画を登録します。
  - **引数**: `group`, `location`
  - **動作**: モーダルが開き、活動日・時間・詳細を入力します。もしその月のExcelファイルが存在しない場合、定期活動や休止期間を反映した上で**全自動で生成**されます。

### `/report` - 活動報告の管理

- `/report open`
  - **説明**: 今日の活動を報告します。
  - **引数**: `group`
  - **動作**: モーダルが開きます。もし今日の活動計画があれば、時間と場所が自動入力されます。報告完了後、指定チャンネルにサイレント通知が送信されます。

### `/excel` - Excelファイルの操作

- `/excel export [year] [month] [as_zip]`
  - **説明**: 指定された年月のExcelファイルを出力します。
  - **引数**:
    - `year` (任意): 西暦年。省略時は今年。
    - `month` (任意): 月。省略時は今月。
    - `as_zip` (任意): `True` (デフォルト)でzip形式、`False`で生ファイル。
  - **動作**: 出力前にファイル内の日付を更新し、チャンネルに送信します。

### `/history` - 履歴の閲覧と操作

- `/history report [group] [location] [limit]`
  - **説明**: 過去の活動報告を検索・表示します。
  - **引数**: `group`, `location`, `limit` で結果を絞り込めます。
  - **動作**: ページめくり可能な一覧が表示され、各報告を「削除」ボタンで安全に取り消せます。

- `/history unreported`
  - **説明**: 報告漏れの活動計画を一覧表示します。
  - **動作**: 表示された各計画を「活動なしとして報告」ボタンで簡単に処理できます。

### `/remind` - カスタムリマインダー

- `/remind add`
  - **説明**: 「ドメイン更新」のような単発・定期タスクを登録します。
- `/remind list`
  - **説明**: 登録済みのタスクを一覧表示し、「編集」「削除」が可能です。

### `/schedule` - スケジュール基盤の設定

- `/schedule regular add`
  - **説明**: 「毎週〇曜日は〇〇班」のような定期活動を登録します。
- `/schedule regular list`
  - **説明**: 登録済みの定期活動を一覧表示します。

- `/schedule off-period add`
  - **説明**: 長期休業やテスト期間などの活動休止期間を登録します。
- `/schedule off-period list`
  - **説明**: 登録済みの活動休止期間を一覧表示します。

### `/config` - Botの基本設定

- `/config show`: 現在のBot設定（顧問名、学生名、選択肢リストなど）を表示します。
- `/config set advisor <名前>`: 顧問名を変更します。
- `/config set student_rep <名前>`: 代表学生名を変更します。
- `/config group add/remove <名前>`: グループの選択肢を編集します。
- `/config location add/remove <名前>`: 場所の選択肢を編集します。
  - **【重要】** 選択肢を変更した後は、`/admin restart` でBotを再起動すると、各コマンドの引数に反映されます。

### `/admin` - 管理者用コマンド

- `/admin restart`
  - **説明**: Botを安全に再起動します。設定変更を反映させる際に使用します。
  - **権限**: サーバーの管理者のみ実行可能です。
