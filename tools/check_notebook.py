"""Validate and execute every plain-Python notebook cell in an isolated process.

This verifies computational execution without requiring a local Jupyter server.
It deliberately does not claim a Colab-browser or Jupyter-kernel integration test.
"""

from base64 import b64encode
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import argparse
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def worker(notebook_path: Path, output_path: Path, workspace: Path) -> None:
    notebook = json.loads(notebook_path.read_text())
    if notebook.get("nbformat") != 4 or not notebook.get("cells"):
        raise ValueError("Expected a nonempty v4 notebook.")
    os.environ["WEALTHLAB_NOTEBOOK_ROOT"] = str(workspace)
    os.environ["WEALTHLAB_SKIP_WIDGETS"] = "1"
    scope = {"__name__": "__main__"}
    execution_count = 0
    outputs = []

    def capture(value):
        if isinstance(value, dict) and "_image" in value:
            payload = {"image/png": b64encode(Path(value["_image"]).read_bytes()).decode(),
                       "text/plain": "WealthLab saved figure"}
        elif isinstance(value, dict) and "_html" in value:
            payload = {"text/html": value["_html"], "text/plain": "WealthLab report ready"}
        elif isinstance(value, dict) and "_markdown" in value:
            payload = {"text/markdown": value["_markdown"], "text/plain": value["_markdown"]}
        elif hasattr(value, "_repr_html_"):
            payload = {"text/html": value._repr_html_(), "text/plain": str(value)}
        else:
            payload = {"text/plain": str(value)}
        outputs.append({"output_type": "display_data", "data": payload, "metadata": {}})

    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] != "code":
            continue
        execution_count += 1
        source = "".join(cell["source"])
        if os.getenv("WEALTHLAB_CHECK_SOURCE") == "demo" and source.startswith("# CELL 12"):
            source, changed = re.subn(r'^SOURCE\s*=\s*"yahoo"', 'SOURCE = "demo"', source, count=1, flags=re.M)
            if changed != 1:
                raise ValueError("Could not apply the explicit offline source override.")
        outputs = []
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exec(compile(source, f"notebook-cell-{execution_count}", "exec"), scope)
        if execution_count == 1:
            scope.update(display=capture, Image=lambda filename: {"_image": filename},
                         HTML=lambda value: {"_html": value}, Markdown=lambda value: {"_markdown": value})
        if stdout.getvalue():
            outputs.insert(0, {"output_type": "stream", "name": "stdout", "text": stdout.getvalue()})
        if stderr.getvalue():
            outputs.append({"output_type": "stream", "name": "stderr", "text": stderr.getvalue()})
        cell.update(execution_count=execution_count, outputs=outputs)
    report = scope["RUN"].report_path
    if not report.is_file() or not scope["EXPORT_PATH"].is_file():
        raise AssertionError("Notebook did not create its report and export bundle.")
    # Strip ephemeral machine paths from captured text; keep figures and calculations.
    serialized = json.dumps(notebook, ensure_ascii=False, indent=1)
    serialized = serialized.replace(str(workspace), "<notebook-workspace>")
    output_path.write_text(serialized, encoding="utf-8")
    mode = os.getenv("WEALTHLAB_CHECK_SOURCE", "notebook setting")
    print(f"PASS: all {execution_count} code cells executed; report and ZIP produced (source: {mode}).")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-executed", type=Path)
    parser.add_argument("--source", choices=["demo"], help="Explicit offline override; preserves saved Yahoo outputs")
    parser.add_argument("--worker", nargs=3, metavar=("NOTEBOOK", "OUTPUT", "WORKSPACE"))
    args = parser.parse_args()
    if args.source and args.write_executed:
        parser.error("An offline source override cannot overwrite the notebook's saved Yahoo outputs.")
    if args.worker:
        worker(*(Path(arg) for arg in args.worker))
        return
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="wealthlab-notebook-") as temp:
        temporary = Path(temp)
        target = args.write_executed.resolve() if args.write_executed else temporary / "executed.ipynb"
        # Input and output may be the same file: the worker reads it completely first.
        environment = os.environ.copy()
        environment.pop("FRED_API_KEY", None)
        if args.source:
            environment["WEALTHLAB_CHECK_SOURCE"] = args.source
        checked = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--worker", str(ROOT/"WealthLab_Colab.ipynb"),
             str(target), str(temporary / "project")], cwd=temporary, env=environment,
            capture_output=True, text=True, timeout=180)
        print(checked.stdout, end="")
        if checked.returncode:
            print(checked.stderr, file=sys.stderr)
        checked.check_returncode()
    print(f"Isolated computational notebook check: {time.monotonic()-started:.1f}s.")


if __name__ == "__main__":
    main()
