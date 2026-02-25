"""共通ユーティリティ (utils.py)

ロギング設定とディレクトリ管理を提供する。
"""

import logging
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """標準ロガーを設定して返す"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


def ensure_dirs() -> None:
    """data/ と output/ ディレクトリが存在しない場合は作成する"""
    Path("data").mkdir(exist_ok=True)
    Path("output").mkdir(exist_ok=True)
