"""Validate and execute every plain-Python notebook cell in an isolated process.

This verifies computational execution without requiring a local Jupyter server.
It deliberately does not claim a Colab-browser or Jupyter-kernel integration test.
"""

from base64 import b64encode
from contextlib import redirect_stdout, redirect_stderr
from html.parser import HTMLParser
from pathlib import Path
from zipfile import ZipFile
import argparse
import ast
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def check_embedded_sources(notebook_path: Path) -> None:
    """Fail if maintained modules or embedded support files drift from the notebook."""
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    checked = set()
    supplemental_count = 0
    extras = {"config.py": "currency.py", "report.py": "findings.py", "pipeline.py": "export.py"}
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        source = "".join(cell["source"])
        module = re.match(r"# CELL \d+ \| Build (\w+\.py)", source)
        statements = ast.parse(source).body
        assignments = {stmt.targets[0].id: stmt.value for stmt in statements
                       if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name)}
        if module:
            name = module.group(1)
            for filename, variable in [(name, "module_source"),
                    *([(extras[name], "findings_source")] if name in extras else [])]:
                maintained = (ROOT / "wealthlab" / filename).read_text(encoding="utf-8")
                if ast.literal_eval(assignments[variable]) != maintained:
                    raise AssertionError(f"Embedded source is stale: wealthlab/{filename}")
                checked.add(filename)
        if source.startswith("# CELL 20"):
            mapping = json.loads(ast.literal_eval(assignments["supplemental"].args[0]))
            for filename, content in mapping.items():
                if (ROOT / filename).read_text(encoding="utf-8") != content:
                    raise AssertionError(f"Embedded support file is stale: {filename}")
            supplemental_count = len(mapping)
    if checked != {file.name for file in (ROOT / "wealthlab").glob("*.py")}:
        raise AssertionError("The notebook does not embed every maintained package module.")
    if not supplemental_count:
        raise AssertionError("No embedded support files were checked.")
    print(f"PASS: {len(checked)} embedded modules and {supplemental_count} support files match the repository.")


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
    class EntryLinks(HTMLParser):
        def __init__(self):
            super().__init__()
            self.targets = []
        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.targets.extend(value for key, value in attrs if key == "href")
    with ZipFile(scope["EXPORT_PATH"]) as archive:
        if archive.testzip() or len(archive.namelist()) != len(set(archive.namelist())):
            raise AssertionError("The exported ZIP is corrupt or contains duplicate entries.")
        links = EntryLinks()
        links.feed(archive.read("START_HERE.html").decode())
        if len(links.targets) != 2 or any(target not in archive.namelist() for target in links.targets):
            raise AssertionError("The exported start page has a broken local link.")
        if archive.read("FINDINGS.md") != (scope["RUN"].output_dir / "FINDINGS.md").read_bytes():
            raise AssertionError("Root exported findings do not match this run.")
        assumptions = json.loads(archive.read("config/current_run.json"))
        if assumptions["research"]["source"] != scope["CONFIG"].source:
            raise AssertionError("The exported source label is stale.")
    print("PASS: exported ZIP integrity, start-page links, current findings, and assumptions.")
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
    check_embedded_sources(ROOT / "WealthLab_Colab.ipynb")
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
