# 05. 定期実行と公開モジュール (Step 5, 6)

## 目標
作成した処理フロー（情報収集 -> 分析 -> スライド生成）を全体として統合し、毎週月曜日に自動で実行し、生成結果を運用環境（Web等）に公開する仕組みを作る。

## 要件
1. **メイン処理の統合 (`src/main.py`)**:
   - `collector`, `analyzer`, `generator` の各モジュールを順番に呼び出すメイン関数 `main()` を作成すること。
   - `python src/main.py` を実行するだけで全工程が完了するように設計する。
2. **自動実行・デプロイ環境 (GitHub Actions推奨)**:
   - レポジトリ直下に `.github/workflows/space_report.yml` を作成すること。

## GitHub Actions による自動化実装方針

以下のステップを実行するワークフロー (`YAML`) を記述すること。

1. **トリガー (Cron)**:
   ```yaml
   on:
     schedule:
       - cron: '0 0 * * 1'  # UTC月曜 0:00 (JST月曜 9:00)
     workflow_dispatch:     # 手動実行用
   ```
2. **実行環境**: `ubuntu-latest`
3. **ステップ構成**:
   - リポジトリの Checkout
   - Python環境のセットアップ (例: Python 3.10)
   - 依存関係のインストール (`pip install -r requirements.txt`)
   - メインスクリプトの実行 (`python src/main.py`)
     - ※この際、GitHub Secrets に設定した `GEMINI_API_KEY` などを環境変数として渡すこと。
   - 成果物の公開:
     - 生成されたスライドファイル (`output/*.pptx` または `output/*.html`) を、`actions/upload-artifact` でアーティファクトとして保存する。
     - もしくは、プロジェクト自体を GitHub Pages として公開し、特定のブランチ（例: `gh-pages` ブランチ）に生成されたHTMLファイルを Push するステップを組むこと。(Step 5 "Webサイト(HP)公開モジュールの実装" を満たすため)

## Claude Code への注意点
GitHub Actionsの設定ファイル等を作成・変更する場合は、実行時にどのような機密情報が扱われ、どこにPushされるのかをユーザー（人間）に事前説明し、承認を得てから実装に進むこと。
