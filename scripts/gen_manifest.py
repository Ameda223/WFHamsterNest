# scripts/gen_manifest.py
import hashlib
import json
from pathlib import Path

# 需要计算哈希的目录
TARGET_DIR = Path("luascripts")
# 仓库根目录（用于计算相对路径）
ROOT_DIR = Path(".")
# update.json 文件路径
MANIFEST_PATH = Path("update.json")

def sha256_file(filepath: Path) -> str:
    """计算文件的 SHA256 哈希值"""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    if not TARGET_DIR.exists():
        print(f"目录 {TARGET_DIR} 不存在，跳过。")
        return

    # 1. 计算所有目标文件的哈希
    hashes = {}
    for file in TARGET_DIR.rglob("*"):
        if file.is_file():
            # 相对于仓库根目录计算路径，保留 luascripts/ 前缀
            rel_path = file.relative_to(ROOT_DIR).as_posix()
            hashes[rel_path] = sha256_file(file)

    # 2. 读取或初始化 update.json 结构
    if not MANIFEST_PATH.exists():
        # 如果文件不存在，创建一个基础结构
        # manifest = {
        #     "version": "1.0.0",
        #     "data_version": 1,
        #     "base_url": "https://raw.githubusercontent.com/Ameda223/WFHamsterNest/main/",
        #     "files": []
        # }
        return

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    # 3. 重建 files 列表，填入新的 sha256
    new_files = []
    for rel_path, hash_val in hashes.items():
        new_files.append({
            "src": rel_path,
            "dest": rel_path,
            "sha256": hash_val
        })
    
    # 按路径排序，保持输出稳定（避免每次提交顺序错乱）
    new_files.sort(key=lambda x: x["src"])
    manifest["files"] = new_files

    # 4. 写回 update.json
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"已更新 {MANIFEST_PATH}，共 {len(new_files)} 个文件。")

if __name__ == "__main__":
    main()