"""GameLogger 单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

from src.logger import GameLogger


class TestGameLogger:
    """GameLogger 测试套件。"""

    def test_log_creates_file(self, tmp_path: Path) -> None:
        """日志调用后文件存在, 内容为合法 JSON, 且包含 ts 和 type 字段。"""
        logger = GameLogger("abc123", log_dir=tmp_path)
        logger.log("game_start", players=["Alice", "Bob"])
        logger.close()

        log_file = tmp_path / "game-abc123.jsonl"
        assert log_file.exists()

        record = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert "ts" in record
        assert record["type"] == "game_start"
        assert record["players"] == ["Alice", "Bob"]

    def test_log_multiple_records(self, tmp_path: Path) -> None:
        """多次 log 调用产生多行 JSONL。"""
        logger = GameLogger("multi", log_dir=tmp_path)
        logger.log("event_a", value=1)
        logger.log("event_b", value=2)
        logger.log("event_c", value=3)
        logger.close()

        lines = (tmp_path / "game-multi.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3

        records = [json.loads(line) for line in lines]
        assert records[0]["type"] == "event_a"
        assert records[1]["type"] == "event_b"
        assert records[2]["type"] == "event_c"

    def test_log_flushes_immediately(self, tmp_path: Path) -> None:
        """不调用 close(), 内容仍然可读。"""
        logger = GameLogger("flush", log_dir=tmp_path)
        logger.log("instant", msg="hello")

        # 不调用 close(), 直接读取文件
        content = (tmp_path / "game-flush.jsonl").read_text(encoding="utf-8").strip()
        assert content != ""

        record = json.loads(content)
        assert record["type"] == "instant"

        logger.close()

    def test_log_handles_unicode(self, tmp_path: Path) -> None:
        """中文字符在日志中保持不变。"""
        logger = GameLogger("unicode", log_dir=tmp_path)
        logger.log("chat", speaker="预言家", message="今晚查验了3号玩家")
        logger.close()

        record = json.loads(
            (tmp_path / "game-unicode.jsonl").read_text(encoding="utf-8").strip()
        )
        assert record["speaker"] == "预言家"
        assert record["message"] == "今晚查验了3号玩家"

    def test_close_is_idempotent(self, tmp_path: Path) -> None:
        """多次调用 close() 不抛异常。"""
        logger = GameLogger("idempotent", log_dir=tmp_path)
        logger.log("event")
        logger.close()
        logger.close()  # 第二次调用应该安全
