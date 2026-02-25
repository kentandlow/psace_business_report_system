"""Gemini API による分析・要約モジュール (Step 3)

data/raw_news.json を読み込み、30 枚スライド分の構造化 JSON を生成して
data/analyzed_report.json に保存する。
"""

import json
import os
import time
from datetime import date
from pathlib import Path

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

SYSTEM_INSTRUCTION = """あなたは世界最高の宇宙ビジネスアナリストです。
提供された生データを分析し、エグゼクティブや投資家向けに毎週の宇宙ビジネス動向レポートをスライド形式で出力します。

出力形式の厳格なルール:
- 必ず JSON 配列のみを返してください。Markdown のコードブロック（```json など）は不要です。
- 各要素は {"slide_number": int, "title": str, "content": [str, ...], "sources": [str, ...]} の形式にしてください。
- content は 1 枚あたり 4〜5 点の箇条書きにしてください（各 60 字以内）。
- sources には出典 URL または出典名を含めてください。
- 日本語で出力してください。"""


# ---------------------------------------------------------------------------
# プロンプト生成
# ---------------------------------------------------------------------------


def _build_category_prompt(
    category_label: str,
    items: list[dict],
    slide_start: int,
    slide_count: int,
) -> str:
    news_text = "\n\n".join(
        f"[{i + 1}] タイトル: {item['title']}\n"
        f"    URL: {item['url']}\n"
        f"    概要: {item['summary'][:500]}\n"
        f"    日時: {item.get('published', '不明')}"
        for i, item in enumerate(items[:30])  # 最大 30 件
    )
    return (
        f"以下は今週の「{category_label}」に関するニュース一覧です。\n\n"
        f"{news_text}\n\n"
        f"上記を分析して、スライド {slide_start} 番から "
        f"{slide_start + slide_count - 1} 番の {slide_count} 枚分の内容を "
        f"JSON 配列で出力してください。\n"
        f'形式: [{{"slide_number": <番号>, "title": "<タイトル>", '
        f'"content": ["<箇条書き1>", ...], "sources": ["<URL>", ...]}}]\n'
        f"JSON 配列のみ返してください。"
    )


def _build_insight_prompt(
    all_slides: list[dict],
    slide_start: int,
    slide_count: int,
) -> str:
    summary = "\n".join(
        f"[スライド{s['slide_number']}] {s['title']}: "
        + " / ".join(s.get("content", [])[:2])
        for s in all_slides
    )
    return (
        "以下は今週のレポート全体の要約です。\n\n"
        f"{summary}\n\n"
        "全体を踏まえて、エグゼクティブ・投資家向けの考察と展望スライドを "
        f"スライド {slide_start} 番から {slide_start + slide_count - 1} 番の "
        f"{slide_count} 枚分、JSON 配列で出力してください。\n"
        f'形式: [{{"slide_number": <番号>, "title": "<タイトル>", '
        f'"content": ["<箇条書き1>", ...], "sources": []}}]\n'
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

        return json.loads(text)

    except json.JSONDecodeError as exc:
        raw = locals().get("text", "")
        logger.error(
            "JSON パース失敗: %s\nレスポンス冒頭: %.300s", exc, raw
        )
        return []
    except Exception as exc:
        logger.error("Gemini API 呼び出し失敗: %s", exc)
        return []


def _placeholder_slides(label: str, start: int, count: int, message: str) -> list[dict]:
    """データ取得失敗時のプレースホルダースライドを生成する"""
    return [
        {
            "slide_number": start + i,
            "title": f"{label} ({i + 1})",
            "content": [message],
            "sources": [],
        }
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------


def analyze() -> list[dict]:
    """raw_news.json を Gemini API で分析し data/analyzed_report.json に保存する"""
    ensure_dirs()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("環境変数 GEMINI_API_KEY が取得できませんでした。ActionsのSecretsや.envの設定を確認してください。")
        raise EnvironmentError(
            "環境変数 GEMINI_API_KEY が設定されていません。"
        )

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=SYSTEM_INSTRUCTION,
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )

    logger.info("=== Gemini API 分析開始 ===")

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
            "content": [
                f"レポート生成日: {date.today().isoformat()}",
                "対象期間: 過去 7 日間",
                "情報源: SpaceNews / Google News / arXiv 等",
                "対象地域: 日本・米国・欧州・中国",
            ],
            "sources": [],
        },
        {
            "slide_number": 2,
            "title": "目次",
            "content": [
                "1. 宇宙政策ニュース（スライド 3〜8）",
                "2. 最新研究内容（スライド 9〜14）",
                "3. 宇宙ビジネスニュース（スライド 15〜20）",
                "4. 資金調達ニュース（スライド 21〜26）",
                "5. 考察と展望（スライド 27〜30）",
            ],
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

        prompt = _build_category_prompt(label, cat_items, plan["start"], plan["count"])
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

    return all_slides


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    analyze()
