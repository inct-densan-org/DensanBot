# ROADMAP

## 1. BOT の使用目的（推測）

本 BOT は「部活動運営の証跡管理」を主目的としたシステムです。

- 日々の活動計画/実績を Discord で収集
- 提出形式（Excel）へ自動反映
- 報告漏れ・期限管理を通知で補助

## 2. 追加機能提案

優先度高:
- 履歴操作時の Excel 即時再同期
- 監査ログ（誰がいつ何を変更したか）
- データ整合性チェックコマンド（JSON/Excel 差分検出）
- エクスポート先多重化（Discord + SharePoint）

優先度中:
- 報告日指定（当日以外の遡及入力）
- CSV/JSON バックアップ自動化
- 管理者向けダッシュボード

## 3. Python 継続 vs JavaScript 移行

結論: **当面は Python 継続推奨**。

理由:
- 既存資産が `discord.py + openpyxl` に集約
- Excel 帳票更新は Python が扱いやすい
- 現機能規模では移行コストが大きい

JS/TS 移行を検討する条件:
- Web UI を本格的に開発する
- Node サービス群へ統合する
- Graph 連携や認可を TypeScript で統一する

## 4. SharePoint / Teams 自動配置（非個人依存）

### 案A: Power Automate（短期最適）

- Bot から HTTP Trigger Flow へファイル送信
- Flow が SharePoint に「ファイル作成」
- 接続は個人ではなく組織管理のサービスアカウント

長所:
- Bot 側で Graph 認証を持たずに済む
- 導入が比較的速い

注意:
- Flow 所有権/接続先の引継ぎ設計が必要

### 案B: Microsoft Graph app-only（長期本命）

- Entra ID アプリ登録 + client credentials
- `Sites.Selected` で対象サイト限定
- Bot から Graph API へ直接 PUT アップロード

長所:
- 個人依存を最小化
- 長期運用の統制に向く

注意:
- 管理者承認・権限設計・秘密情報管理が必要

### 案C: 同期クライアント利用

- サーバに同期フォルダを置く方式
- 個人依存や運用事故が起きやすく非推奨

## 5. 推奨方針

- フェーズ1（早期）: Power Automate 導入
- フェーズ2（恒久）: Graph app-only + Sites.Selected へ移行

これにより、短期で実装しつつ最終的に非個人依存を達成できます。
