"""成果物保存モジュール (Step 4) — Markdown → PDF 変換版

data/analyzed_report.md を読み込み、コンサル風の CSS を適用した HTML に変換し
xhtml2pdf (純 Python) で PDF 化して output/ に保存する。
.md ファイルも同時に output/ に保存する。

出力ファイル:
  output/space_report_YYYYMMDD.pdf  ← メイン成果物（コンサル風デザイン）
  output/space_report_YYYYMMDD.md   ← ソーステキスト（バックアップ兼共有用）
"""

import io
from datetime import date
from pathlib import Path

import markdown
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xhtml2pdf import pisa

from utils import ensure_dirs, setup_logger

logger = setup_logger(__name__)

INPUT_PATH = Path("data/analyzed_report.md")
OUTPUT_DIR = Path("output")


# ---------------------------------------------------------------------------
# 日本語フォント検索
# ---------------------------------------------------------------------------

_FONT_NAME = "ReportFont"

def _find_cjk_font() -> str | None:
    """OS 別に日本語フォントファイルのパスを探索して返す（見つからなければ None）"""
    candidates = [
        # Windows
        "C:/Windows/Fonts/YuGothR.ttc",
        "C:/Windows/Fonts/yugothic.ttf",
        "C:/Windows/Fonts/YuGothM.ttc",
        "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
        # Linux (apt: fonts-noto-cjk)
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJKjp-Regular.otf",
    ]
    for path in candidates:
        if Path(path).exists():
            logger.info("日本語フォント発見: %s", path)
            return path
    logger.warning("日本語フォントが見つかりませんでした。文字化けの可能性があります。")
    return None


def _register_font(font_path: str) -> bool:
    """reportlab に日本語フォントを直接登録する。

    xhtml2pdf の @font-face 処理（ファイルコピー）を使わずに
    reportlab の pdfmetrics を経由することで TTC ファイルの読み込みエラーを回避する。
    """
    try:
        pdfmetrics.registerFont(TTFont(_FONT_NAME, font_path, subfontIndex=0))
        logger.info("フォント登録完了: %s → '%s'", font_path, _FONT_NAME)
        return True
    except Exception as exc:
        logger.warning("フォント登録失敗: %s", exc)
        return False


# ---------------------------------------------------------------------------
# CSS スタイルシート（xhtml2pdf / CSS2 互換）
# ---------------------------------------------------------------------------

def _build_css(font_registered: bool) -> str:
    """コンサル風 CSS を構築する。
    reportlab にフォントが登録済みの場合は ReportFont を使用する。
    @font-face は使わず、pdfmetrics 登録済みのフォント名を直接 font-family で指定する。
    """
    font_family_decl = (
        f"{_FONT_NAME}, Helvetica, sans-serif" if font_registered
        else "Helvetica, sans-serif"
    )

    return f"""
@page {{
    size: A4;
    margin: 20mm 16mm 22mm 16mm;
}}

body {{
    font-family: {font_family_decl};
    font-size: 9.5pt;
    line-height: 1.65;
    color: #1a1a2e;
}}

/* ── 見出し ──────────────────────────────── */
h1 {{
    font-size: 18pt;
    color: #0d1b2a;
    border-bottom: 2px solid #4fb3bf;
    padding-bottom: 6px;
    margin-top: 6px;
    margin-bottom: 4px;
}}

h2 {{
    font-size: 12pt;
    color: #ffffff;
    background-color: #0d3b52;
    padding: 6px 12px;
    margin-top: 20px;
    margin-bottom: 6px;
}}

h3 {{
    font-size: 10.5pt;
    color: #0d3b52;
    background-color: #eaf4f5;
    padding: 3px 8px;
    border-left: 4px solid #4fb3bf;
    margin-top: 12px;
    margin-bottom: 4px;
}}

h4 {{
    font-size: 9.5pt;
    color: #2e86c1;
    margin-top: 8px;
    margin-bottom: 3px;
}}

/* ── 本文 ─────────────────────────────────── */
p {{
    margin: 4px 0;
}}

ul, ol {{
    padding-left: 16px;
    margin: 4px 0;
}}

li {{
    margin-bottom: 2px;
}}

strong {{
    color: #0a2540;
}}

hr {{
    border: 1px solid #4fb3bf;
    margin: 12px 0;
}}

blockquote {{
    border-left: 3px solid #4fb3bf;
    margin: 6px 2px;
    padding: 4px 10px;
    background-color: #f0f8f9;
    color: #2e4057;
}}

code {{
    background-color: #f0f4f8;
    font-size: 8pt;
    padding: 1px 3px;
}}

/* ── 表 ──────────────────────────────────── */
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 8px 0 12px 0;
    font-size: 8.5pt;
}}

th {{
    background-color: #2e86c1;
    color: #ffffff;
    padding: 5px 8px;
    text-align: left;
    font-weight: bold;
    border: 1px solid #1a6fa0;
}}

td {{
    padding: 4px 8px;
    border: 1px solid #c8d8e8;
    vertical-align: top;
}}
"""


# ---------------------------------------------------------------------------
# Markdown → スタイル付き HTML
# ---------------------------------------------------------------------------

def _to_styled_html(md_text: str, css: str, today_str: str) -> str:
    """Markdown テキストを CSS 付きの完全な HTML 文字列に変換する"""
    md_proc = markdown.Markdown(
        extensions=["tables", "fenced_code"],
    )
    body_html = md_proc.convert(md_text)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>宇宙ビジネス週次戦略インテリジェンスレポート {today_str}</title>
  <style>{css}</style>
</head>
<body>
{body_html}
</body>
</html>"""


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def generate() -> Path:
    """analyzed_report.md を PDF（+ MD）に変換して output/ に保存する。

    Returns:
        Path: 保存した PDF ファイルのパス（PDF 生成失敗時は MD ファイルのパス）
    """
    ensure_dirs()

    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"{INPUT_PATH} が見つかりません。先に analyzer.py を実行してください。"
        )

    today_str = date.today().strftime("%Y%m%d")
    md_text = INPUT_PATH.read_text(encoding="utf-8")

    # ── .md ファイルを保存 ─────────────────────────────────
    md_path = OUTPUT_DIR / f"space_report_{today_str}.md"
    md_path.write_text(md_text, encoding="utf-8")
    logger.info("Markdown 保存完了: %s (%d 文字)", md_path, len(md_text))

    # ── Markdown → HTML → PDF 変換 ────────────────────────
    pdf_path = OUTPUT_DIR / f"space_report_{today_str}.pdf"
    try:
        logger.info("PDF 変換中（xhtml2pdf）...")
        font_path = _find_cjk_font()
        font_registered = _register_font(font_path) if font_path else False
        css = _build_css(font_registered)
        html_str = _to_styled_html(md_text, css, today_str)

        with open(pdf_path, "wb") as pdf_file:
            result = pisa.CreatePDF(
                src=io.StringIO(html_str),
                dest=pdf_file,
                encoding="utf-8",
            )

        if result.err:
            raise RuntimeError(f"xhtml2pdf エラーコード: {result.err}")

        size_kb = pdf_path.stat().st_size // 1024
        logger.info("PDF 保存完了: %s (%d KB)", pdf_path, size_kb)
        return pdf_path

    except Exception as exc:
        logger.warning(
            "PDF 変換に失敗しました（%s）。Markdown ファイルを成果物として使用します。",
            exc,
        )
        return md_path


if __name__ == "__main__":
    generate()
