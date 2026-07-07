from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def generate_monthly_presentation(deck_data_path: Path | str, output_pptx: Path | str) -> dict[str, str]:
    deck_data_path = Path(deck_data_path).resolve()
    output_pptx = Path(output_pptx).resolve()
    output_pptx.parent.mkdir(parents=True, exist_ok=True)

    workspace = Path(tempfile.gettempdir()) / "codex-presentations" / "project-health-reporting-agent"
    tmp_dir = workspace / "tmp"
    preview_dir = tmp_dir / "preview"
    qa_dir = tmp_dir / "qa"
    inspect_path = output_pptx.with_suffix(f"{output_pptx.suffix}.inspect.ndjson")

    tmp_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)
    qa_dir.mkdir(parents=True, exist_ok=True)

    node_bin = _resolve_node_bin()
    setup_script = _resolve_presentations_setup_script()
    builder_source = Path(__file__).with_name("monthly_deck_builder.mjs")
    builder_script = tmp_dir / builder_source.name
    shutil.copyfile(builder_source, builder_script)

    _run_quiet(
        [str(node_bin), str(setup_script), "--workspace", str(tmp_dir)],
        "presentation workspace setup",
    )
    _run_quiet(
        [
            str(node_bin),
            str(builder_script),
            str(deck_data_path),
            str(output_pptx),
            str(preview_dir),
            str(qa_dir),
            str(inspect_path),
        ],
        "monthly deck generation",
    )

    return {
        "pptx_path": str(output_pptx),
        "inspect_path": str(inspect_path),
        "preview_dir": str(preview_dir),
        "qa_dir": str(qa_dir),
    }


def _resolve_node_bin() -> Path:
    env_value = os.getenv("PROJECT_HEALTH_NODE_BIN")
    if env_value:
        candidate = Path(env_value).expanduser()
        if candidate.exists():
            return candidate

    bundled_candidate = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
        / "bin"
        / "node"
    )
    if bundled_candidate.exists():
        return bundled_candidate

    which_node = shutil.which("node")
    if which_node:
        return Path(which_node)

    raise RuntimeError(
        "Could not find a Node.js runtime for PowerPoint generation. "
        "Set PROJECT_HEALTH_NODE_BIN to override."
    )


def _resolve_presentations_setup_script() -> Path:
    env_value = os.getenv("PROJECT_HEALTH_PRESENTATION_SETUP")
    if env_value:
        candidate = Path(env_value).expanduser()
        if candidate.exists():
            return candidate

    root = Path.home() / ".codex" / "plugins" / "cache" / "openai-primary-runtime" / "presentations"
    candidates = sorted(root.glob("*/skills/presentations/container_tools/setup_artifact_tool_workspace.mjs"))
    if candidates:
        return candidates[-1]

    raise RuntimeError(
        "Could not find the bundled presentation setup script required for deck generation. "
        "Set PROJECT_HEALTH_PRESENTATION_SETUP to override."
    )


def _run_quiet(command: list[str], step_name: str) -> None:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return

    details = "\n".join(
        part.strip()
        for part in [result.stdout, result.stderr]
        if part and part.strip()
    )
    if not details:
        details = f"{step_name} exited with code {result.returncode}."
    raise RuntimeError(f"Failed during {step_name}.\n{details}")
