# モデルの軽量化およびバグ修正・安定化計画

## 1. 背景と課題
GitHub Actionsでの定期実行において、`429 You exceeded your current quota`（クォータ制限超過）エラーが発生し、処理が異常終了（exit code 1）する問題が確認されました。
原因は、現状の無料枠（Free Tier）では `gemini-2.5-pro` モデルの1日あたりのリクエスト数や入力トークン数の上限が非常に厳しく設定されており、ニュースの生データを一括で処理する現在のプロンプトではAPIの制限にすぐ到達してしまうためです。

安定した自動生成システムを実現するために、推論速度が速く無料枠の制限が余裕のある **軽量モデルへのダウングレード** を行う必要があります。

## 2. 修正指示（Claude Codeへのタスク）

Claude Codeを使用して、以下の改修を実行してください。

### ① AIモデルの変更 (`src/analyzer.py`)
クォータ制限を回避するため、重い `gemini-2.5-pro` から軽量かつ高速なモデルである **`gemini-2.5-flash`**（または `gemini-2.0-flash`）にモデル名を変更してください。
* `src/analyzer.py` の `model_name="gemini-2.5-pro"` を `model_name="gemini-2.5-flash"` に修正します。
* 注意点として、FlashモデルはProモデルに比べて複雑な指示の厳守力が若干下がるケースがあります。そのため、プロンプトの「出力の制約」部分に「絶対に提供された形式（Markdownの見出し、表など）を崩さずに完全なレポートを出力すること」という強い念押しの記述を追記して、品質を担保してください。

### ② パッケージ依存関係の明示によるバグ予防 (`requirements.txt`)
`src/generator.py` 内で `reportlab` のモジュール（`from reportlab.pdfbase.ttfonts import TTFont` など）を直接インポートして使用していますが、現在の `requirements.txt` には `reportlab` 自体の記載がありません（`xhtml2pdf` の依存パッケージとして暗黙的にインストールされ動いている状態です）。
* 意図しないバージョン競合や将来の依存関係アップデートによるビルドエラーを未然に防ぐため、`requirements.txt` に明示的に `reportlab>=4.0`（または適切なバージョン）を追加してください。

---

## Claude Code への実行コマンド例（プロンプト）

Claude Codeを起動して、以下のプロンプトを実行してください。

```text
GitHub Actionsの実行において、「429 You exceeded your current quota」エラーが発生しました。Gemini 2.5 Proの制限に引っかかっていることが原因です。システムの安定稼働のため、plan/10_model_downgrade_and_bug_fixes.md を読み込み、以下のタスクを実行してください。

1. `src/analyzer.py` 内のモデルを `gemini-2.5-pro` から `gemini-2.5-flash` に変更してください。あわせて、Flashモデルでも出力形式（Markdownの構造や表）が崩れないように、プロンプトの指示をより厳格に修正してください。
2. `src/generator.py` で直接インポートしている `reportlab` を `requirements.txt` に明示的に追記し、将来の環境構築バグを予防してください。
3. すべての実装が完了したら、ローカル環境で一度実行テストを行い、APIエラーとならずに最終的なPDF出力まで成功するか確認してください。
```
