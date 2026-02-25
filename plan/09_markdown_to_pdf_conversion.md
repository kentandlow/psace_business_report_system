# 詳細レポートのPDF出力実装とPPTX完全撤廃計画

## 1. 背景と課題
Markdown形式のアプローチに変更したものの、以下の課題が残っています。

1. **GitHub Actions 側に PPTX 出力の設定が残ったままになっている**:
   `.github/workflows/space_report.yml` の artifact のアップロードパスがまだ `output/*.pptx` になっているため、結果が保存されていません。
2. **成果物のポータビリティ**:
   Markdown（.md）のままだとビジネス用の共有がしづらいため、最終的な成果物として美しく整形された **PDFファイル** を出力する仕様を追加します。

## 2. 実装計画（Claude Code への指示）

Claude Codeを使用して、以下の 2 つの改修を実行してください。

### ① `generator.py` の改修：Markdown から PDF への変換機能の追加
現在の `generator.py` は、単に `analyzed_report.md` を `output/` にコピーしているだけのスルーパス処理になっています。これに機能を追加し、Markdown を PDF に変換して保存するように変更してください。

* **使用ライブラリの追加**: 
  `markdown` や `pdfkit` (wkhtmltopdf 依存)、あるいは純 Python で動く軽量な `md2pdf`、`weasyprint` などのライブラリを新しく選定して `requirements.txt` に追加してください。（環境依存の少ないライブラリを推奨します）
* **PDFデザイン**:
  コンサルタントのレポートのように、シンプルなCSSスタイル（例えば、H1/H2の青い装飾、表の罫線、読みやすい余白、`lead_message`部分の強調など）を埋め込んでからPDF化する処理を作成してください。
* **出力先**:
  `output/space_report_YYYYMMDD.pdf` と、元テキストである `.md` ファイルの両方を出力するようにしてください。

### ② `space_report.yml` の修正：成果物のアップロード対象変更
GitHub Actionsのワークフロー・ファイルを修正し、生成された PDF（および MD）をアーティファクトとして保存するようにしてください。

* `.github/workflows/space_report.yml` の 77 行目付近:
  `path: output/*.pptx` を `path: output/*`（あるいは `output/*.pdf` と `output/*.md`）に変更してください。

---

## Claude Code への実行コマンド例（プロンプト）

Claude Codeを起動して、以下のプロンプトを実行してください。

```text
仕様の微調整を行います。plan/09_markdown_to_pdf_conversion.md を読み込み、以下のタスクを実行してください。

1. generator.py を本格的に改修し、analyzer.py が生成した Markdown テキストから美しい PDF を生成して output/ ディレクトリに保存する機能を追加してください（必要なら requirements.txt に markdown や pdf変換ライブラリを追加）。コンサル風のシンプルなCSSを挟んでからPDF化すると完璧です。
2. .github/workflows/space_report.yml を修正し、Artifactsのアップロード先パスを output/*.pptx から output/*.pdf (および .md) に修正し、古い pptx の記述を完全に抹消してください。
3. すべての実装が完了したら、ローカルで通しテストを実行し、問題なくPDFが出力されることを確認してください。
```
