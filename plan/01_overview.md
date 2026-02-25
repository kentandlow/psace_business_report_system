# 共通要件とアーキテクチャ概要 (Overview)

このフォルダ（`plan/`）内のドキュメントは、Claude Codeが「宇宙ビジネス動向レポート自動生成システム」を構築するための**詳細な実装指示書**です。
Claude Codeは各ステップのドキュメントを読み、それに従ってコードの記述と実行を行ってください。

## 1. ディレクトリ構成
システムは以下のディレクトリ構成で実装すること。

```text
space_business_report_system/
├── src/                # Pythonソースコード
│   ├── main.py         # エントリーポイント・全体フロー制御
│   ├── collector.py    # 情報収集モジュール (Step 2)
│   ├── analyzer.py     # Geminiによる要約・分析モジュール (Step 3)
│   ├── generator.py    # スライド生成モジュール (Step 4)
│   └── utils.py        # 共通ユーティリティ（ロギング等）
├── data/               # 収集した生データの一時保存用 (Git管理外)
├── output/             # 生成されたスライドやHTMLの保存用 (Git管理外)
├── plan/               # 実装指示書 (このフォルダ)
├── .env.example        # 環境変数テンプレート
├── .gitignore          # Git除外設定
├── requirements.txt    # 依存パッケージ一覧
└── README.md
```

## 2. 開発言語・主要ライブラリ
- **言語**: Python 3.10+
- **主要ライブラリ**:
  - `google-generativeai`: Gemini APIの呼び出し
  - `feedparser`: RSSフィードの解析
  - `requests`, `beautifulsoup4`: Webスクレイピング
  - `python-pptx`: プレゼンテーション(PPTX)の生成
  - `python-dotenv`: 環境変数の読み込み
  - `schedule`: （ローカルテスト用）定期実行

## 3. 共通ルール・エラーハンドリング
- **APIキーの扱い**: `os.environ` を通じて `.env` から取得すること。絶対にコード内にハードコードしてはいけない。
- **ロギング**: `print` だけでなく、標準の `logging` モジュールを使用して、処理の進捗とエラーをコンソールに出力させること。
- **データ出力**: デバッグや後続テストがしやすいように、各モジュールの入出力は適宜 JSON 形式等で `data/` フォルダに出力・保存するように組むこと。
- **安全確認**: システムの中核（たとえばGitHub ActionsへのPushや、大量APIの呼び出しを最初に行う際）には、必ず「実行してよいですか？」とユーザーの承認を求めるプロセスを踏むこと。
