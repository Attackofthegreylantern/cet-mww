"""Regenerate missing/stale reading files without changing vocabulary data."""
import argparse
import json

from storage import LexiconStore
from word_export import render_word


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true", help="Create a separate Word preview without replacing the open notebook")
    args = parser.parse_args()
    store = LexiconStore()
    if args.preview:
        with store._locked():
            data = store._load_unlocked()
            path = store.data_dir / "CET-Lexicon-双栏细蓝线预览.docx"
            if (store.data_dir / ("~$" + path.name[2:])).exists() or (store.data_dir / ("~$" + path.name)).exists():
                raise SystemExit("请先关闭双栏预览文件，再重新生成。")
            store._atomic_bytes(path, render_word(data))
            result = {"preview_path": str(path), "entry_count": len(data["entries"])}
    else:
        result = store.initialize()
    print(json.dumps(result, ensure_ascii=False, indent=2))
