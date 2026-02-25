"""Gemini API による分析・要約モジュール (Step 3) — MBB グレードアップ版

data/raw_news.json を読み込み、マッキンゼー/BCG レベルの
戦略インサイト・グラフデータを含む 30 枚スライド分の JSON を生成して
data/analyzed_report.json に保存する。
"""

import json
import os
import time
from datetime import date
from pathlib import Path
from typing import Any

import google.generativeai as genai

from utils import ensure_dirs, setup_logger

logger = setup_logger(__name__)

INPUT_PATH = Path("data/raw_news.json")
OUTPUT_PATH = Path("data/analyzed_report.json")

# ---------------------------------------------------------------------------
# スライド構成定義（全 30 枚）
# スライド 1〜2  : 表紙・目次（固定）
# スライド 3〜8  : 宇宙政策ニュース（6 枚）
# スライド 9〜14 : 最新研究内容（6 枚）
# スライド 15〜20: 宇宙ビジネスニュース（6 枚）
# スライド 21〜26: 資金調達ニュース（6 枚）
# スライド 27〜30: 考察と展望（4 枚）
# ---------------------------------------------------------------------------

CATEGORIES = {
    "policy":   "宇宙政策ニュース（日米欧中）",
    "research": "最新研究内容",
    "business": "宇宙ビジネスニュース",
    "funding":  "資金調達ニュース",
}

SLIDE_PLAN = {
    "policy":   {"start": 3,  "count": 6},
    "research": {"start": 9,  "count": 6},
    "business": {"start": 15, "count": 6},
    "funding":  {"start": 21, "count": 6},
    "insight":  {"start": 27, "count": 4},
}

# ---------------------------------------------------------------------------
# MBB レベル System Instruction
# ---------------------------------------------------------------------------

SYSTEM_INSTRUCTION = """あなたは、マッキンゼー・アンド・カンパニーとBCG（ボストン・コンサルティング・グループ）双方での実務経験を持つ、宇宙ビジネス専門のシニア・ストラテジスト（最上位パートナー）です。

【厳守すべき思考規律】
1. 事実（Fact）の羅列は絶対禁止。提供されたニュースはあくまで根拠データとして活用し、必ず以下の問いに答えること。
   - So What?（だから何が重要なのか）
   - Impact（業界・競合・投資環境にどう影響するか）
   - Forward-looking（次の1〜3ヶ月で何が起きるか）
2. 各スライドの lead_message は「そのページで最も言いたい結論を1文で」。経営幹部はここだけ読めば本質を把握できる品質を目指すこと。
3. グラフや表のデータ（values）は、ニュース記事の件数・記述内容・業界知識から論理的に推計・集計すること。絶対精度より「業界トレンドを正確に表現すること」を優先。「推計値」「論理的推論に基づく概算」として明示すること。

【出力スキーマ — 厳格に遵守すること】
JSON 配列を返すこと。各要素は以下のスキーマ:
{
  "slide_number": <整数>,
  "title": "<セクションタイトル（25字以内）>",
  "lead_message": "<最重要結論・メインメッセージ（40字以内、体言止め不可・断言口調）>",
  "insights": [
    "<So What? の観点で（60字以内）>",
    "<Impact の観点で（60字以内）>",
    "<Forward-looking の観点で（60字以内）>"
  ],
  "visuals": {
    "type": "<'chart_bar' | 'chart_pie' | 'table' | 'none'>",
    "title": "<グラフ・表のタイトル（空の場合は空文字）>",
    "labels": ["<ラベル1>", "<ラベル2>", ...],
    "values": [<数値1>, <数値2>, ...],
    "headers": ["<列ヘッダー1>", "<列ヘッダー2>", ...],
    "rows": [["<セル値1>", "<セル値2>", ...], ...]
  },
  "sources": ["<出典URLまたは媒体名>", ...]
}

【visuals フィールドの使い分け】
- chart_bar / chart_pie: labels と values を設定。headers と rows は空配列 []。
- table: headers と rows を設定。labels と values は空配列 []。
- none: labels, values, headers, rows はすべて空配列 []。

【必須】Markdown コードブロック（```json など）は使用禁止。JSON 配列のみ出力すること。
【必須】日本語で出力すること。"""


# ---------------------------------------------------------------------------
# 拡張 JSON スキーマ対応のプレースホルダー生成
# ---------------------------------------------------------------------------

def _placeholder_slides(label: str, start: int, count: int, message: str) -> list[dict]:
    """データ取得失敗時のプレースホルダースライドを生成する"""
    return [
        {
            "slide_number": start + i,
            "title": f"{label} ({i + 1})",
            "lead_message": "データ取得に失敗しました",
            "insights": [message],
            "visuals": {
                "type": "none",
                "title": "",
                "labels": [],
                "values": [],
                "headers": [],
                "rows": [],
            },
            "sources": [],
        }
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# プロンプト生成
# ---------------------------------------------------------------------------

CATEGORY_SLIDE_DESIGN = {
    "policy": [
        "政策全体サマリー: 日米欧中の政策動向を俯瞰し、最重要変化を特定。visuals.type='chart_bar' で各国の政策活動量（推計件数）を比較。",
        "最重要政策トピック①: 最もインパクトが大きいニュースを深掘り。So What? と業界への Impact を明示。適切な visuals を選択。",
        "最重要政策トピック②: 2番目に重要なニュースを深掘り。table で比較軸を示すと効果的。",
        "地政学的リスクと機会: 国際競争・協力関係の変化を分析。chart_bar で各国の動向強度を比較。",
        "規制環境の変化: 新たな規制・許認可の動きとビジネスインパクトを分析。",
        "政策セクション総括: 今後1ヶ月の注目ポイントと投資家への示唆。visuals.type='none'。",
    ],
    "research": [
        "研究動向サマリー: 今週の主要研究テーマを俯瞰。chart_pie で研究分野別の件数比率を示す。",
        "ブレークスルー研究①: 最も商業応用可能性が高い研究を深掘り。",
        "ブレークスルー研究②: 2番目に重要な研究を深掘り。",
        "技術成熟度と商業化ギャップ: 研究から事業化までの距離感を分析。table で技術別のTRL（技術成熟度）推計を示す。",
        "競争上の示唆: どの技術領域で誰がリードしているか分析。chart_bar で機関別の論文数推計を示す。",
        "研究セクション総括: 投資家が注目すべき研究トレンドと時間軸。",
    ],
    "business": [
        "ビジネス動向サマリー: 今週の主要ビジネストレンドを俯瞰。chart_bar で企業/分野別の注目度を比較。",
        "主要ビジネス案件①: 最重要ビジネスニュースを深掘り。競合・市場への影響を分析。",
        "主要ビジネス案件②: 2番目の重要案件を深掘り。",
        "市場構図の変化: 既存プレイヤーと新興企業の勢力図変化を分析。table で主要企業の動向比較。",
        "バリューチェーン分析: どのセグメントで付加価値が生まれているか。chart_bar でセグメント別市場規模推計。",
        "ビジネスセクション総括: M&A・提携・IPOの観点での投資家示唆。",
    ],
    "funding": [
        "資金調達全体像: 今週の調達額・件数の全体サマリー。chart_bar でセクター別推計調達額を比較。",
        "注目調達案件①: 最も注目すべき資金調達案件の深掘り。投資家の意図と業界への影響を分析。",
        "注目調達案件②: 2番目の注目案件を深掘り。",
        "投資トレンド分析: どのステージ・分野に資金が集まっているかの分析。chart_pie でステージ別比率。",
        "日本のスタートアップ動向: 国内宇宙スタートアップの資金調達状況と課題。",
        "資金調達セクション総括: VCが今注目するテーマと今後の調達見通し。table で注目企業リスト。",
    ],
}

INSIGHT_SLIDE_DESIGN = [
    "今週の最重要変化点: レポート全体を通じて最も重要な変化を1枚で整理。table で変化点・インパクト・タイムラインを構造化。",
    "業界構図の変化シナリオ: 今週の出来事が業界の中長期構図をどう変えるか分析。chart_bar で各シナリオの確率推計（%）。",
    "投資家向け総合示唆: 今週のニュースから導かれる投資判断の材料を整理。table で投資テーマ・推奨アクション・リスク。",
    "来週の注目ポイント: 今後1週間で注視すべきイベント・発表・動向。visuals.type='none'。",
]


def _build_category_prompt(
    category_label: str,
    category_key: str,
    items: list[dict],
    slide_start: int,
    slide_count: int,
) -> str:
    news_text = "\n\n".join(
        f"[{i + 1}] タイトル: {item['title']}\n"
        f"    URL: {item['url']}\n"
        f"    概要: {item['summary'][:500]}\n"
        f"    日時: {item.get('published', '不明')}"
        for i, item in enumerate(items[:30])
    )

    designs = CATEGORY_SLIDE_DESIGN.get(category_key, [])
    design_instructions = "\n".join(
        f"  - スライド {slide_start + i} ({i + 1}枚目): {d}"
        for i, d in enumerate(designs[:slide_count])
    )

    return (
        f"以下は今週の「{category_label}」に関するニュース一覧です（{len(items[:30])} 件）。\n\n"
        f"{news_text}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"タスク: 上記を分析し、スライド {slide_start}〜{slide_start + slide_count - 1} の "
        f"{slide_count} 枚分のコンサル品質スライドデータを JSON 配列で出力してください。\n\n"
        "各スライドの設計指針（必ず従うこと）:\n"
        f"{design_instructions}\n\n"
        "重要な品質基準:\n"
        "- lead_message は結論を断言する1文（40字以内）\n"
        "- insights は So What / Impact / Forward-looking の3視点\n"
        "- visuals のグラフデータは記事から論理的に推計した値（推計であることは sources に明示）\n"
        "- table は headers（列名）と rows（データ行の配列）を必ず設定\n\n"
        "JSON 配列のみ返してください。"
    )


def _build_insight_prompt(
    all_slides: list[dict],
    slide_start: int,
    slide_count: int,
) -> str:
    summary = "\n".join(
        f"[スライド{s['slide_number']}] {s['title']}: {s.get('lead_message', '')} / "
        + " / ".join(s.get("insights", [])[:1])
        for s in all_slides
        if s.get("slide_number", 0) >= 3
    )

    design_instructions = "\n".join(
        f"  - スライド {slide_start + i} ({i + 1}枚目): {d}"
        for i, d in enumerate(INSIGHT_SLIDE_DESIGN[:slide_count])
    )

    return (
        "以下はレポート全体の週次サマリーです。\n\n"
        f"{summary}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "タスク: 全体を総合的に分析し、エグゼクティブ・投資家向けの「考察と展望」セクションを "
        f"スライド {slide_start}〜{slide_start + slide_count - 1} の {slide_count} 枚で生成してください。\n\n"
        "各スライドの設計指針（必ず従うこと）:\n"
        f"{design_instructions}\n\n"
        "JSON 配列のみ返してください。"
    )


# ---------------------------------------------------------------------------
# Gemini API 呼び出し
# ---------------------------------------------------------------------------


def _call_gemini(model: genai.GenerativeModel, prompt: str) -> list[dict]:
    """Gemini に問い合わせて JSON リストを返す。失敗時は空リストを返す。"""
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()

        # Markdown コードブロックが含まれる場合は除去
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )

        result = json.loads(text)
        logger.debug("Gemini 出力サンプル: %s", json.dumps(result[:1], ensure_ascii=False)[:300])
        return result

    except json.JSONDecodeError as exc:
        raw = locals().get("text", "")
        logger.error("JSON パース失敗: %s\nレスポンス冒頭: %.400s", exc, raw)
        return []
    except Exception as exc:
        logger.error("Gemini API 呼び出し失敗: %s", exc)
        return []


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------


def analyze() -> list[dict]:
    """raw_news.json を Gemini API で分析し data/analyzed_report.json に保存する"""
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
        model_name="gemini-2.5-flash",
        system_instruction=SYSTEM_INSTRUCTION,
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.4,  # 戦略的洞察の生成のため若干高めに設定
        ),
    )

    logger.info("=== Gemini API 分析開始（MBB グレード）===")

    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"{INPUT_PATH} が見つかりません。先に collector.py を実行してください。"
        )

    items: list[dict] = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    logger.info("生データ読み込み: %d 件", len(items))

    # カテゴリ別に分類
    categorized: dict[str, list[dict]] = {cat: [] for cat in CATEGORIES}
    for item in items:
        cat = item.get("category", "")
        if cat in categorized:
            categorized[cat].append(item)

    # --- 表紙・目次スライド（固定生成） ---
    all_slides: list[dict] = [
        {
            "slide_number": 1,
            "title": "宇宙ビジネス動向 週次レポート",
            "lead_message": "戦略コンサルタント視点で今週の宇宙ビジネスを総括する",
            "insights": [
                f"レポート生成日: {date.today().isoformat()}",
                "対象期間: 過去 7 日間",
                "情報源: SpaceNews / Google News / arXiv 等",
            ],
            "visuals": {
                "type": "none",
                "title": "",
                "labels": [],
                "values": [],
                "headers": [],
                "rows": [],
            },
            "sources": [],
        },
        {
            "slide_number": 2,
            "title": "目次",
            "lead_message": "5 つのセクションで宇宙ビジネスの全体像を俯瞰する",
            "insights": [
                "1. 宇宙政策ニュース（スライド 3〜8）",
                "2. 最新研究内容（スライド 9〜14）",
                "3. 宇宙ビジネスニュース（スライド 15〜20）",
                "4. 資金調達ニュース（スライド 21〜26）",
                "5. 考察と展望（スライド 27〜30）",
            ],
            "visuals": {
                "type": "none",
                "title": "",
                "labels": [],
                "values": [],
                "headers": [],
                "rows": [],
            },
            "sources": [],
        },
    ]

    # --- カテゴリ別スライド生成 ---
    for cat, label in CATEGORIES.items():
        plan = SLIDE_PLAN[cat]
        cat_items = categorized.get(cat, [])
        logger.info(
            "カテゴリ '%s': %d 件 → スライド %d〜%d を生成",
            label, len(cat_items),
            plan["start"], plan["start"] + plan["count"] - 1,
        )

        if not cat_items:
            logger.warning("  データなし。プレースホルダーを挿入します。")
            all_slides.extend(
                _placeholder_slides(label, plan["start"], plan["count"],
                                    "今週は該当するニュースがありませんでした。")
            )
            continue

        prompt = _build_category_prompt(
            label, cat, cat_items, plan["start"], plan["count"]
        )
        slides = _call_gemini(model, prompt)

        if slides:
            all_slides.extend(slides)
        else:
            logger.warning("  Gemini 応答なし。プレースホルダーを使用します。")
            all_slides.extend(
                _placeholder_slides(label, plan["start"], plan["count"],
                                    "（分析データの取得に失敗しました）")
            )

        time.sleep(2)  # API レートリミット対策

    # --- 考察と展望スライド生成 ---
    insight_plan = SLIDE_PLAN["insight"]
    logger.info(
        "考察・展望スライド生成（スライド %d〜%d）",
        insight_plan["start"],
        insight_plan["start"] + insight_plan["count"] - 1,
    )
    insight_prompt = _build_insight_prompt(
        all_slides, insight_plan["start"], insight_plan["count"]
    )
    insight_slides = _call_gemini(model, insight_prompt)

    if insight_slides:
        all_slides.extend(insight_slides)
    else:
        all_slides.extend(
            _placeholder_slides("考察と展望", insight_plan["start"],
                                insight_plan["count"], "（考察データの取得に失敗しました）")
        )

    # スライド番号でソート
    all_slides.sort(key=lambda s: s.get("slide_number", 0))

    OUTPUT_PATH.write_text(
        json.dumps(all_slides, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(
        "分析完了: %d 枚のスライドデータを %s に保存", len(all_slides), OUTPUT_PATH
    )

    # ---- 出力品質の簡易チェック ----
    _quality_check(all_slides)

    return all_slides


def _quality_check(slides: list[dict[str, Any]]) -> None:
    """生成された JSON が期待スキーマを満たしているかログで確認する"""
    valid_types = {"chart_bar", "chart_pie", "table", "none"}

    def _is_valid(s: dict[str, Any]) -> bool:
        has_lead = bool(s.get("lead_message"))
        has_insights = isinstance(s.get("insights"), list) and len(s.get("insights", [])) > 0
        has_visuals_type = s.get("visuals", {}).get("type") in valid_types
        return has_lead and has_insights and has_visuals_type

    ng_slides = [s.get("slide_number") for s in slides if not _is_valid(s)]
    ok = len(slides) - len(ng_slides)

    logger.info("品質チェック: OK=%d / 全%d枚", ok, len(slides))
    if ng_slides:
        logger.warning("スキーマ不備スライド: %s", ng_slides)
    else:
        logger.info("全スライドがスキーマを満たしています。")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(override=False)
    analyze()
