"""GameLogger: 将游戏事件以 JSONL 格式写入文件。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class GameLogger:
    """以 JSONL 格式记录游戏事件的日志器。

    每条记录包含 ``ts`` (ISO 时间戳) 和 ``type`` 字段,
    其余字段通过 ``**fields`` 传入。

    Parameters
    ----------
    game_id : str
        游戏唯一标识, 用于构造文件名 ``game-{game_id}.jsonl``。
    log_dir : Path, optional
        日志目录, 默认为 ``logs/``。
    """

    def __init__(self, game_id: str, log_dir: Path | None = None) -> None:
        self._log_dir = log_dir if log_dir is not None else Path("logs")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._log_dir / f"game-{game_id}.jsonl"
        self._file = self._path.open("a", encoding="utf-8")

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def log(self, type: str, **fields: object) -> None:
        """写入一条日志记录。

        Parameters
        ----------
        type : str
            事件类型, 如 ``"day_start"``、``"vote"`` 等。
        **fields
            附加字段, 会直接并入 JSON 对象。
        """
        record: dict[str, object] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": type,
            **fields,
        }
        line = json.dumps(record, ensure_ascii=False)
        self._file.write(line + "\n")
        self._file.flush()

    def close(self) -> None:
        """关闭日志文件。可安全地多次调用。"""
        if self._file and not self._file.closed:
            self._file.close()
