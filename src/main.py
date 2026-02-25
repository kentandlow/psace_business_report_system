"""メインエントリーポイント (Step 5)

python src/main.py を実行するだけで
  1. 情報収集 (collector)
  2. AI 分析・要約 → Markdown レポート生成 (analyzer)
  3. レポート保存 (generator)
の全工程が完了する。
"""

import logging
import sys
from pathlib import Path

# src/ 配下のモジュールを import できるように sys.path を調整
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

from utils import setup_logger

logger = setup_logger("main", logging.INFO)


def main() -> None:
    # .env から環境変数を読み込む
    # GitHub Actions等の既存の環境変数を優先するため override=False とする
    load_dotenv(override=False)

    # ----------------------------------------------------------------
    # Step 1: 情報収集
    # ----------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("【Step 1/3】情報収集を開始します...")
    logger.info("=" * 60)
    try:
        from collector import collect
        items = collect()
        logger.info("  ✓ 収集完了: %d 件", len(items))
    except Exception as exc:
        logger.error("情報収集でエラーが発生しました: %s", exc)
        sys.exit(1)

    # ----------------------------------------------------------------
    # Step 2: AI 分析・Markdown レポート生成
    # ----------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("【Step 2/3】Gemini API 分析を開始します（APIリクエスト: 1回）...")
    logger.info("=" * 60)
    try:
        from analyzer import analyze
        report_path = analyze()
        logger.info("  ✓ 分析完了: %s", report_path)
    except Exception as exc:
        logger.error("AI 分析でエラーが発生しました: %s", exc)
        sys.exit(1)

    # ----------------------------------------------------------------
    # Step 3: 成果物保存
    # ----------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("【Step 3/3】レポート保存を開始します...")
    logger.info("=" * 60)
    try:
        from generator import generate
        output_path = generate()
        logger.info("  ✓ 保存完了: %s", output_path)
    except Exception as exc:
        logger.error("レポート保存でエラーが発生しました: %s", exc)
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("=== 全処理完了 ===")
    logger.info("成果物: %s", output_path)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
