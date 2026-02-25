"""Gemini API による分析・要約モジュール (Step 3) — Markdown レポート版

data/raw_news.json を読み込み、マッキンゼー/BCG レベルの
Markdown 形式の週次戦略インテリジェンスレポートを生成して
data/analyzed_report.md に保存する。

設計方針:
- API リクエスト回数を 1 回に集約しレートリミットエラーを防止する
- JSON スキーマへの依存を廃止し、Markdown テキストを直接生成させる
- gemini-2.5-pro の長文出力能力を活かした圧倒的ボリュームのレポート生成
"""

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import google.generativeai as genai

from utils import ensure_dirs, setup_logger

logger = setup_logger(__name__)

INPUT_PATH  = Path("data/raw_news.json")
OUTPUT_PATH = Path("data/analyzed_report.md")

MAX_ITEMS_PER_CATEGORY = 25  # カテゴリごとの最大ニュース件数

CATEGORIES = {
    "policy":   "宇宙政策動向（日米欧中）",
    "research": "宇宙テクノロジー・研究動向",
    "business": "宇宙ビジネス・企業動向",
    "funding":  "資金調達・投資動向",
}

# ---------------------------------------------------------------------------
# MBB レベル System Instruction
# ---------------------------------------------------------------------------

SYSTEM_INSTRUCTION = """あなたは、マッキンゼー・アンド・カンパニーとBCG（ボストン・コンサルティング・グループ）双方での15年以上の実績を持つ、宇宙ビジネス・宇宙産業専門のシニア・ストラテジスト（マネージングパートナー）です。

あなたのミッションは、提供された宇宙ビジネス関連のニュースを素材として、グローバルな宇宙産業のエグゼクティブや機関投資家が意思決定に使用できる「週次戦略インテリジェンスレポート」をMarkdown形式で作成することです。

【品質基準 — 絶対厳守】
1. 「Factの羅列」は最低品質です。提供されたニュースは「根拠データ」に過ぎません。あなたが書くのは「インサイト（洞察）」です。
2. 各重要トピックで必ず以下の3点を明示してください:
   - **So What?（だから何が重要か）**: この出来事の本質的意味を1文で断言する
   - **Industry Impact（業界への影響）**: 競合・投資環境・サプライチェーンへの具体的な波及効果
   - **Future Outlook（今後の展望）**: 今後1〜3ヶ月で何が起きるかを具体的かつ大胆に予測する
3. 各セクションに最低1つのMarkdown表（| 列名 | ... |）を含めること。定量比較・フレームワーク・マトリクス等を積極的に活用すること。
4. 数値・金額はニュースの記述と業界知識から論理的に推計し、必ず「（推計）」と明示すること。
5. 文体は断言的・直接的。「〜と思われます」「〜かもしれません」は使用禁止。"""


# ---------------------------------------------------------------------------
# プロンプト構築
# ---------------------------------------------------------------------------

def _build_report_prompt(
    categorized: dict[str, list[dict[str, Any]]],
    today: str,
) -> str:
    """全カテゴリのニュースを1本のMarkdownレポート生成プロンプトに統合する"""
    section_blocks: list[str] = []
    total_count = 0

    for cat_key, cat_label in CATEGORIES.items():
        cat_raw: list[dict[str, Any]] = categorized.get(cat_key, [])
        n_take = min(len(cat_raw), MAX_ITEMS_PER_CATEGORY)
        items = [cat_raw[i] for i in range(n_take)]
        total_count += len(items)

        if not items:
            section_blocks.append(
                f"### {cat_label}\n（今週は該当するニュースがありませんでした）"
            )
            continue

        news_lines = "\n".join(
            f"- **{item.get('title', '（タイトルなし）')}** "
            f"({item.get('published', '日時不明')[:10]})  "
            f"出典: {item.get('source', '不明')}  "
            f"概要: {item.get('summary', '')[:300]}"
            for item in items
        )
        section_blocks.append(f"### {cat_label}（{len(items)} 件）\n{news_lines}")

    news_block = "\n\n".join(section_blocks)

    return f"""レポート作成日: {today}
収集ニュース総数: {total_count} 件（直近30日間）

## 分析対象ニュース一覧

{news_block}

---

## タスク

上記のニュース全件を分析し、以下の構成でMarkdown形式の週次戦略インテリジェンスレポートを作成してください。
**各セクションを省略せず、十分なボリュームで記述してください。**

## 出力するレポートの構成（この見出し構成に厳密に従うこと）

# 宇宙ビジネス週次戦略インテリジェンスレポート
レポート日: {today}

---

## エグゼクティブ・サマリー
（今週最も重要な変化と結論を5点、各1〜2文で断言する）

---

## 1. 宇宙政策動向（日米欧中）

### 1-1. 今週の政策概況
（今週の政策動向を俯瞰し、主要トレンドを記述。**Markdown表で国別動向を整理すること**）

### 1-2. 最重要政策トピック
（最もインパクトの大きい政策ニュースを深掘り分析する）

**So What?**: ...
**Industry Impact**: ...
**Future Outlook**: ...

### 1-3. 地政学的リスクと機会
（国際競争・協力関係の変化を分析。推計値を用いた比較表を含めること）

### 1-4. セクション総括・投資家示唆
（このセクションから導かれる投資・事業戦略上の示唆を断言する）

---

## 2. 宇宙テクノロジー・研究動向

### 2-1. 今週の研究概況
（今週の主要研究テーマを俯瞰。**分野別Markdown表**で件数・重要度を整理すること）

### 2-2. 注目技術・ブレークスルー
（商業応用可能性が最も高い研究・技術を深掘り分析する）

**So What?**: ...
**Industry Impact**: ...
**Future Outlook**: ...

### 2-3. 技術成熟度と商業化タイムライン
（主要技術の現在地と事業化までの距離感を**Markdown表（TRL・商業化目標年等）**で整理する）

### 2-4. セクション総括
（投資家が注目すべき技術トレンドと時間軸）

---

## 3. 宇宙ビジネス・企業動向

### 3-1. 今週のビジネス概況
（今週の主要ビジネストレンドを俯瞰。**企業別動向Markdown表**で整理すること）

### 3-2. 主要案件の深掘り分析
（最も重要なビジネスニュースを深掘り分析する）

**So What?**: ...
**Industry Impact**: ...
**Future Outlook**: ...

### 3-3. 競合環境・市場構図の変化
（既存プレイヤーと新興企業の勢力図変化を分析。**競合比較表**を含めること）

### 3-4. セクション総括・M&A・IPO示唆
（M&A・提携・IPOの観点での投資家示唆）

---

## 4. 資金調達・投資動向

### 4-1. 今週の資金調達概況
（今週の調達額・件数・主要案件。**セクター別調達サマリーMarkdown表**を含めること）

### 4-2. 注目投資案件の分析
（最も注目すべき資金調達案件の深掘り）

**So What?**: ...
**Industry Impact**: ...
**Future Outlook**: ...

### 4-3. 投資トレンドとVC注目テーマ
（どのステージ・分野に資金が集まっているか。**ステージ・分野別の推計比率表**を含めること）

### 4-4. 日本スタートアップ動向
（国内宇宙スタートアップの資金調達状況と課題）

---

## 5. 総合考察と戦略的示唆

### 5-1. 今週最大の業界変化
（今週起きた最重要変化をインパクト順に**Markdown表（変化点・影響・タイムライン）**で整理する）

### 5-2. 業界構図の変化シナリオ
（今週の出来事が業界の中長期構図をどう変えるか。シナリオ分析を行い、**各シナリオの確率推計（%）**を示す）

### 5-3. 投資家向けアクションアジェンダ
（今週のニュースから導かれる具体的な投資アクションを、**優先度・推奨アクション・リスク**のMarkdown表で整理する）

### 5-4. 来週の注目ポイント
（今後1週間で注視すべきイベント・発表・動向を**Markdown表**で整理する）

---

## 出力の制約（必ず守ること）
- 日本語で出力すること
- Markdownの見出し・表・太字・箇条書きを積極的に活用すること
- 各主要セクション（1〜5）は最低400字以上のボリュームで記述すること
- レポート全体で最低3000字以上の内容にすること"""


# ---------------------------------------------------------------------------
# Gemini API 呼び出し
# ---------------------------------------------------------------------------

def _call_gemini(model: genai.GenerativeModel, prompt: str) -> str:
    """Gemini に問い合わせて Markdown テキストを返す。失敗時は例外を送出する。"""
    logger.info("プロンプト長: %d 文字", len(prompt))
    response = model.generate_content(
        prompt,
        request_options={"timeout": 600},  # 長文出力のため10分タイムアウト
    )
    text = response.text.strip()
    logger.info("レスポンス長: %d 文字", len(text))
    return text


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def analyze() -> Path:
    """raw_news.json を Gemini API で分析し data/analyzed_report.md に保存する。

    Returns:
        Path: 生成された Markdown ファイルのパス
    """
    ensure_dirs()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error(
            "環境変数 GEMINI_API_KEY が取得できませんでした。"
            "ActionsのSecretsや.envの設定を確認してください。"
        )
        raise EnvironmentError("環境変数 GEMINI_API_KEY が設定されていません。")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name="gemini-2.5-pro",
        system_instruction=SYSTEM_INSTRUCTION,
        generation_config=genai.types.GenerationConfig(
            temperature=0.4,
            max_output_tokens=16384,
        ),
    )

    logger.info("=== Gemini API 分析開始（Markdown モード・1リクエスト集約）===")

    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"{INPUT_PATH} が見つかりません。先に collector.py を実行してください。"
        )

    items: list[dict[str, Any]] = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    logger.info("生データ読み込み: %d 件", len(items))

    # カテゴリ別に分類
    categorized: dict[str, list[dict[str, Any]]] = {cat: [] for cat in CATEGORIES}
    for item in items:
        cat = item.get("category", "")
        if cat in categorized:
            categorized[cat].append(item)

    for cat_key, cat_label in CATEGORIES.items():
        logger.info(
            "  %s: %d 件", cat_label, len(categorized.get(cat_key, []))
        )

    today = date.today().isoformat()
    prompt = _build_report_prompt(categorized, today)

    try:
        markdown_text = _call_gemini(model, prompt)
    except Exception as exc:
        logger.error("Gemini API 呼び出し失敗: %s", exc)
        raise

    OUTPUT_PATH.write_text(markdown_text, encoding="utf-8")
    logger.info(
        "Markdown レポート生成完了: %s (%d 文字)", OUTPUT_PATH, len(markdown_text)
    )

    return OUTPUT_PATH


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(override=False)
    analyze()
