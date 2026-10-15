# scripts/fetch_wf_data.py
"""
抓取 Warframe 紫卡统计与 Prime 价格数据。
- 每 12 小时运行一次（Actions 触发）
- 文件名精确到日：riven_YYYY-MM-DD.json / prime_YYYY-MM-DD.json
- 同一天多次运行会覆盖当天文件
- 自动清理超过 60 天的旧文件
"""
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

RETENTION_DAYS = 60
RETRIES = 3
TIMEOUT = 30

# (文件名前缀, API 地址)
TARGETS = [
    ("riven", "https://api.warframestat.us/pc/rivens"),
    ("prime", "https://api.warframestat.us/wfinfo/prices"),
]


def fetch(url: str, retries: int = RETRIES):
    """带重试的 GET。"""
    headers = {
        "User-Agent": "WFHamsterNest-Updater/1.0 (+https://github.com/Ameda223/WFHamsterNest)",
        "Accept": "application/json",
    }
    last_err = None
    for i in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            print(f"  [{i + 1}/{retries}] 失败: {e}", file=sys.stderr)
            if i < retries - 1:
                time.sleep(3 * (i + 1))
    raise RuntimeError(f"抓取失败: {url}") from last_err


def cleanup_old_files(prefix: str, retention_days: int = RETENTION_DAYS) -> int:
    """
    删除 data/ 下匹配 prefix_*.json 且文件修改时间超过 retention_days 的文件。
    返回删除数量。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    removed = 0
    for f in DATA_DIR.glob(f"{prefix}_*.json"):
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            f.unlink()
            print(f"  [清理] 删除过期文件: {f.name}")
            removed += 1
    return removed


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")

    for prefix, url in TARGETS:
        print(f"抓取: {url}")
        try:
            data = fetch(url)
        except Exception as e:
            print(f"  [错误] {e}", file=sys.stderr)
            continue

        dest = DATA_DIR / f"{prefix}_{today}.json"
        dest.write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        size_kb = dest.stat().st_size / 1024
        print(f"  已保存: {dest.name}  ({size_kb:.1f} KB)")

        removed = cleanup_old_files(prefix)
        if removed:
            print(f"  清理了 {removed} 个超过 {RETENTION_DAYS} 天的旧文件")

    print("完成。")


if __name__ == "__main__":
    main()
