"""Export a run with matching findings, configuration, and a working entry page."""

from html import escape
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import ZipFile, ZIP_DEFLATED
import json
import os

from .config import ClientConfig, ResearchConfig

if TYPE_CHECKING:
    from .pipeline import ProjectRun


def export_run(run: "ProjectRun", config: ResearchConfig, client: ClientConfig,
               project_root: str | Path, destination: str | Path | None = None) -> Path:
    """Bundle generated outputs and source, excluding the live-data cache.

    The ZIP's root documents describe this specific run. The maintained GitHub
    README and recorded Yahoo findings are not substituted for freshly generated
    results, particularly when an explicit synthetic run is exported.
    """
    root = Path(project_root).resolve()
    if run.manifest["config"] != config.to_dict() or run.manifest["client"] != client.to_dict():
        raise ValueError("Export assumptions must match the completed run.")
    report_relative = run.report_path.resolve().relative_to(root).as_posix()
    if not (root / "wealthlab").is_dir() or not (root / "requirements.txt").is_file():
        raise FileNotFoundError("Export from the project workspace after materializing source and documentation.")
    target = Path(destination).resolve() if destination else root / "WealthLab_Run.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    source_label = run.manifest["source_label"]
    quality = run.manifest["quality"]
    notebook_url = "https://colab.research.google.com/github/KhalilChaaban/Wealthlab-portfolio-analytics/blob/main/WealthLab_Colab.ipynb"
    readme = f"""# WealthLab — generated {config.source.upper()} run

{source_label}

Reporting currency: **{config.currency}**. Price observations: {quality['first_observation']}
to {quality['last_observation']}. Run ID: `{run.manifest['run_id']}`.

- Open `START_HERE.html`, or [open the offline report]({report_relative}).
- Read [the findings from this run](FINDINGS.md).
- See the report's assumptions and its sibling `run_manifest.json` for provenance.
- [Open the maintained Colab notebook]({notebook_url}). The notebook itself is a separate download.

The included guide documents the methodology and the original saved Yahoo case.
The report and root findings in this export describe the current run. Synthetic
outputs are labeled as demonstrations. Historical backtests and forward scenarios
are educational models. This is a personal project developed with AI assistance.

To reproduce using the exported assumptions:

```bash
python -m pip install -r requirements-live.txt
python -m unittest discover -s tests -v
python -m wealthlab --config config/current_run.json --root .
```

Yahoo mode requires provider access; FRED mode requires your own key. An explicit
demo run can use `requirements.txt` without live adapters. Raw live-market caches
and credentials are excluded.
"""
    start = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>WealthLab | Generated run</title><style>'
        'body{background:#f3f6fa;color:#142d4e;font:17px/1.7 system-ui,sans-serif;'
        'max-width:900px;margin:50px auto;padding:24px}main{background:white;'
        'padding:36px;border-radius:12px}a{color:#008d83}h1{line-height:1.2}'
        '</style><main><h1>WealthLab</h1><p>' + escape(source_label) + '</p><p>'
        + escape(f"Reporting currency: {config.currency}. Run: {run.manifest['run_id']}.")
        + '</p><p><a href="' + escape(report_relative, quote=True)
        + '">Open this run’s offline report</a></p><p><a href="FINDINGS.md">'
        'Read this run’s findings</a></p><p>See README.md for reproduction instructions.'
        '</p></main></html>'
    )
    generated = {
        "START_HERE.html": start,
        "README.md": readme,
        "FINDINGS.md": (run.output_dir / "FINDINGS.md").read_text(encoding="utf-8"),
        "config/current_run.json": json.dumps({"research": config.to_dict(), "client": client.to_dict()}, indent=2),
    }
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
            for folder in (run.output_dir, *(root / name for name in
                           ("wealthlab", "tests", "docs", "tools", "config", ".github"))):
                for file in sorted(folder.rglob("*")):
                    member = file.relative_to(root).as_posix()
                    if file.is_file() and "__pycache__" not in file.parts and member not in generated:
                        archive.write(file, member)
            for name in ("LICENSE", "pyproject.toml", ".gitignore", "requirements.txt",
                         "requirements-live.txt", "requirements-tested.txt", "requirements-colab.txt"):
                if (root / name).is_file():
                    archive.write(root / name, name)
            for name, content in generated.items():
                archive.writestr(name, content)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
