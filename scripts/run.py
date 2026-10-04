"""Run baseline checks and preserve logs in scratch; Python standard library only."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time

from collect_environment import collect, sha256


REPO = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def logged_command(argv, directory, label, timeout):
    start = time.monotonic()
    try:
        result = subprocess.run(argv, cwd=REPO, capture_output=True, text=True,
                                timeout=timeout)
        stdout, stderr = result.stdout, result.stderr
        record = {"argv": argv, "cwd": str(REPO), "returncode": result.returncode}
    except (OSError, subprocess.TimeoutExpired) as error:
        stdout, stderr = "", str(error) + "\n"
        record = {"argv": argv, "cwd": str(REPO), "returncode": None, "error": str(error)}
    record["elapsed_host_seconds"] = time.monotonic() - start
    (directory / f"{label}.stdout.txt").write_text(stdout)
    (directory / f"{label}.stderr.txt").write_text(stderr)
    write_json(directory / f"{label}.json", record)
    if stdout:
        print(stdout, end="")
    if stderr:
        print(stderr, end="", file=sys.stderr)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("env", "check", "drm-smoke"))
    parser.add_argument("--scratch-root", type=Path,
                        default=Path("/scratch/apple-m2-playground"))
    parser.add_argument("--device", default="/dev/dri/renderD128")
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    root = args.scratch_root.resolve() / "runs"
    root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(
        prefix=f"{started.strftime('%Y%m%dT%H%M%SZ')}-{args.command}-", dir=root))
    write_json(directory / "environment.json", collect(REPO))
    summary = {"command": args.command, "started_utc": started.isoformat(),
               "device": args.device if args.command == "drm-smoke" else None,
               "source_sha256": {str(path.relative_to(REPO)): sha256(path)
                                 for path in [REPO / "tests/drm_smoke.c", *sorted(
                                     (REPO / "scripts").glob("*.py"))]},
               "passed": False, "commands": []}
    compiler = shlex.split(os.environ.get("CC", "cc"))
    flags = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-O2"]

    if args.command == "check":
        # Parse without writing .pyc files into the repository.
        for source in sorted((REPO / "scripts").glob("*.py")):
            compile(source.read_text(), str(source), "exec")
        result = logged_command(compiler + flags + ["-fsyntax-only", "tests/drm_smoke.c"],
                                directory, "compile", 60)
        summary["commands"].append(result)
        summary["passed"] = result["returncode"] == 0
    elif args.command == "drm-smoke":
        binary = directory / "drm_smoke"
        result = logged_command(compiler + flags + ["tests/drm_smoke.c", "-o", str(binary)],
                                directory, "compile", 60)
        summary["commands"].append(result)
        if result["returncode"] == 0:
            result = logged_command([str(binary), args.device], directory, "probe", 10)
            summary["commands"].append(result)
        summary["passed"] = result["returncode"] == 0
    else:
        summary["passed"] = True

    summary["completed_utc"] = datetime.now(timezone.utc).isoformat()
    summary["scope"] = {
        "env": "Environment capture only; missing optional tools are recorded.",
        "check": "Python and C syntax checks only; no hardware execution.",
        "drm-smoke": "DRM open/version query only; no shader execution.",
    }[args.command]
    write_json(directory / "summary.json", summary)
    print(f"{'PASS' if summary['passed'] else 'FAIL'}: {summary['scope']}")
    print(f"Run record: {directory}")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
