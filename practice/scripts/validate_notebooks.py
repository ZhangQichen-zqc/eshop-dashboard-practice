import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = ROOT / "notebooks"


def main():
    files = sorted(NOTEBOOK_DIR.glob("*.ipynb"))
    if not files:
        raise SystemExit("没有找到 Notebook")
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["nbformat"] == 4, path
        assert data["cells"], path
        assert any(c["cell_type"] == "code" for c in data["cells"]), path
        assert any(c["cell_type"] == "markdown" for c in data["cells"]), path
        print("OK", path.name, "cells=", len(data["cells"]))
    print("Notebook JSON 结构验证通过。")


if __name__ == "__main__":
    main()
