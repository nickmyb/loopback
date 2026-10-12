"""状态文件读写：原子写 + version 字段（CLAUDE.md 不变量 6）。

原子写：先写同目录下的临时文件，再 os.replace。进程在任何时刻崩溃，都不会留下写了一半的 JSON。
version：数据格式升级时据此迁移。迁移脚本放在后补项，现在只做检查。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class StoreError(RuntimeError):
    pass


def write_json(path: Path, data: dict[str, Any], *, version: int) -> None:
    """原子写 JSON：写同目录的临时文件并 fsync，再用 os.replace 替换。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"version": version, **data}, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_json(path: Path, *, version: int) -> dict[str, Any] | None:
    """文件不存在返回 None；版本比代码新时报错，避免旧代码误改新格式的数据。"""
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    found = data.get("version", 0)
    if found > version:
        raise StoreError(f"{path} 是 v{found} 格式，当前代码只支持到 v{version}，请升级 loopback")
    return data
