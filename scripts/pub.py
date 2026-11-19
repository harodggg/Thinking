#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
VAULT_DIR = REPO_DIR / "thinking" if (REPO_DIR / "thinking").exists() else REPO_DIR

sys.path.insert(0, str(SCRIPT_DIR))
from distribute import process_file


def find_single_article(query: str | None) -> Path:
    if query:
        p = Path(query).expanduser()
        if p.is_file():
            return p.resolve()

    candidates = [
        f for f in VAULT_DIR.rglob("*.md")
        if not any(part.startswith(".") for part in f.parts) and f.name != "README.md"
    ]
    if not candidates:
        sys.exit(f"未在 {VAULT_DIR} 下找到任何 Markdown 文章")

    if query:
        matched = [f for f in candidates if query.lower() in f.stem.lower()]
        if not matched:
            sys.exit(f"未找到包含「{query}」的文章")
        return max(matched, key=lambda f: f.stat().st_mtime)

    # 无参数时，自动锁定刚刚修改过的最新一篇文章
    return max(candidates, key=lambda f: f.stat().st_mtime)


def main():
    query = " ".join(sys.argv[1:]).strip() or None
    target = find_single_article(query)
    print(f"[目标文章] {target.relative_to(REPO_DIR)}")
    preview_path = process_file(target)
    subprocess.run(["open", "-a", "Google Chrome", str(preview_path)], check=False)


if __name__ == "__main__":
    main()
