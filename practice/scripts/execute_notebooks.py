import json
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = ROOT / "notebooks"


def execute_notebook(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    namespace = {
        "__name__": "__main__",
        "__file__": str(path),
    }
    old_cwd = Path.cwd()
    try:
        import os

        os.chdir(path.parent)
        for index, cell in enumerate(data["cells"], start=1):
            if cell["cell_type"] != "code":
                continue
            source = "".join(cell.get("source", []))
            if not source.strip():
                continue
            exec(compile(source, f"{path.name}:cell-{index}", "exec"), namespace)
    finally:
        import os

        os.chdir(old_cwd)


def main():
    for path in sorted(NOTEBOOK_DIR.glob("*.ipynb")):
        print(f"RUN {path.name}")
        try:
            execute_notebook(path)
        except Exception:
            print(f"FAILED {path.name}")
            traceback.print_exc()
            raise
        print(f"PASS {path.name}")
    print("全部 Notebook 代码单元执行通过。")


if __name__ == "__main__":
    main()
