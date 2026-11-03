# scripts/fetch_wf_data.py
"""
抓取 Warframe 紫卡统计与 Prime 价格数据。
- 每 8 小时运行一次（每天 3 次，Actions 触发）
- 文件名精确到日：riven_YYYYMMDD.json / prime_YYYYMMDD.json
- 同一天多次运行会覆盖当天文件
- 自动清理超过 60 天的旧文件
- 自动修复历史 Prime 数据的 today_vol 异常
"""
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SCRIPT_DIR = Path(__file__).resolve().parent
STATE_FILE = SCRIPT_DIR / "repair_state.json" # 记录修复状态的 json 文件

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


def repair_prime_history():
    """
    修复 Prime 历史数据的 today_vol。
    逻辑：N天的 today_vol = N+1天的 yesterday_vol。
    通过 repair_state.json 记录上次修复的日期，避免重复计算。
    """
    print("开始检查并修复历史 Prime 数据...")
    
    # 1. 获取所有 prime_*.json 文件并排序
    prime_files = sorted(DATA_DIR.glob("prime_*.json"))
    if len(prime_files) < 2:
        print("  Prime 数据文件少于2个，跳过修复。")
        return

    # 2. 读取状态文件，获取上次修复到哪一天
    last_repaired_date = "19700101"
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
                last_repaired_date = state.get("last_repaired_date", "19700101")
        except Exception as e:
            print(f"  [警告] 读取状态文件失败，将从头开始检查: {e}")

    # 去除最后一个文件（今天的文件），因为今天的 today_vol 需要明天的数据来修复
    files_to_process = prime_files[:-1]
    
    if not files_to_process:
        print("  无需修复的文件。")
        return

    modified_count = 0
    latest_processed_date = last_repaired_date

    # 3. 遍历文件进行修复
    for i in range(len(prime_files) - 1):
        current_file = prime_files[i]
        next_file = prime_files[i + 1]
        
        # 从文件名提取日期字符串，如 prime_20261101.json -> 20261101
        current_date = current_file.stem.split("_")[1]
        
        # 如果当前文件日期小于或等于上次修复的日期，说明已经修过了，直接跳过
        if current_date <= last_repaired_date:
            continue

        print(f"  正在修复: {current_file.name} -> 使用 {next_file.name} 的数据")
        
        try:
            with open(current_file, 'r', encoding='utf-8') as f:
                current_data = json.load(f)
            with open(next_file, 'r', encoding='utf-8') as f:
                next_data = json.load(f)
                
            # 建立明天的数据映射：{ 物品名称: 准确的昨日交易量 }
            next_day_yesterday_vol_map = {
                item['name']: item['yesterday_vol'] 
                for item in next_data if 'name' in item and 'yesterday_vol' in item
            }

            file_modified = False
            for item in current_data:
                item_name = item.get('name')
                if item_name in next_day_yesterday_vol_map:
                    new_today_vol = next_day_yesterday_vol_map[item_name]
                    if item.get('today_vol') != new_today_vol:
                        item['today_vol'] = new_today_vol
                        file_modified = True
                        
            if file_modified:
                with open(current_file, 'w', encoding='utf-8') as f:
                    json.dump(current_data, f, ensure_ascii=False, separators=(",", ":"))
                modified_count += 1
                
            latest_processed_date = current_date
            
        except Exception as e:
            print(f"  [错误] 处理文件 {current_file.name} 时出错: {e}")

    # 4. 更新状态文件
    if latest_processed_date != last_repaired_date:
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump({"last_repaired_date": latest_processed_date}, f, indent=4)
            print(f"  状态已更新，记录为: {latest_processed_date}")
        except Exception as e:
            print(f"  [错误] 写入状态文件失败: {e}")
            
    print(f"历史数据修复完成，共更新了 {modified_count} 个文件。")


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

    # 数据抓取完毕后，执行历史数据修复逻辑（只影响 prime）
    repair_prime_history()
    
    print("完成。")


if __name__ == "__main__":
    main()