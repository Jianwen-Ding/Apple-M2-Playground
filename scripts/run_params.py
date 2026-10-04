"""Build and run bounded, read-only Asahi parameter queries; logs go to scratch."""

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


def command(argv, directory, label, timeout):
    started = time.monotonic()
    try:
        result = subprocess.run(argv, cwd=REPO, capture_output=True, text=True,
                                timeout=timeout)
        stdout, stderr = result.stdout, result.stderr
        record = {"argv": argv, "cwd": str(REPO), "returncode": result.returncode}
    except subprocess.TimeoutExpired as error:
        stdout = (error.stdout or b"").decode(errors="replace")
        stderr = (error.stderr or b"").decode(errors="replace") + str(error) + "\n"
        record = {"argv": argv, "cwd": str(REPO), "returncode": None, "error": str(error)}
    except OSError as error:
        stdout, stderr = "", str(error) + "\n"
        record = {"argv": argv, "cwd": str(REPO), "returncode": None, "error": str(error)}
    record["timeout_seconds"] = timeout
    record["elapsed_host_seconds"] = time.monotonic() - started
    (directory / f"{label}.stdout.txt").write_text(stdout)
    (directory / f"{label}.stderr.txt").write_text(stderr)
    write_json(directory / f"{label}.json", record)
    if stderr:
        print(stderr, end="", file=sys.stderr)
    return record, stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="/dev/dri/renderD128")
    parser.add_argument("--repeats", type=int, choices=range(1, 11), default=3)
    parser.add_argument("--scratch-root", type=Path,
                        default=Path("/scratch/apple-m2-playground"))
    args = parser.parse_args()
    root = args.scratch_root.resolve() / "runs"
    root.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    directory = Path(tempfile.mkdtemp(prefix=started.strftime("%Y%m%dT%H%M%SZ-params-"), dir=root))
    summary = {"started_utc": started.isoformat(), "device": args.device,
               "repeats_requested": args.repeats, "passed": False, "commands": [],
               "scope": "Read-only DRM version/global parameter queries; no GPU work.",
               "source_sha256": {str(p.relative_to(REPO)): sha256(p) for p in
                                 [REPO / "tests/drm_params.c", Path(__file__).resolve(),
                                  REPO / "scripts/collect_environment.py"]}}
    try:
        write_json(directory / "environment.json", collect(REPO))
        compiler = shlex.split(os.environ.get("CC", "cc"))
        flags = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-O2"]
        commands = summary["commands"]
        record, _ = command(compiler + ["--version"], directory, "compiler", 10)
        commands.append(record)
        record, output = command(compiler + flags + ["-M", "tests/drm_params.c"],
                                 directory, "dependencies", 60)
        commands.append(record)
        if record["returncode"] != 0:
            return 1
        dependencies = shlex.split(output.replace("\\\n", " ").split(":", 1)[1])
        paths = sorted({str((REPO / p).resolve()) for p in dependencies})
        summary["build_dependency_sha256"] = {p: sha256(p) for p in paths}
        for name in ("asahi_drm.h", "drm.h"):
            for path in paths:
                if Path(path).name == name:
                    (directory / name).write_bytes(Path(path).read_bytes())
                    record, _ = command(["rpm", "-qf", path], directory, f"package-{name}", 10)
                    commands.append(record)
        local = Path("/save/workspace/AGX_Probe/mesa/include/drm-uapi/asahi_drm.h")
        summary["local_reference_header"] = {"path": str(local), "sha256": sha256(local)}
        binary = directory / "drm_params"
        record, _ = command(compiler + flags + ["tests/drm_params.c", "-o", str(binary)],
                            directory, "compile", 60)
        commands.append(record)
        if record["returncode"] != 0:
            return 1
        outputs = []
        for index in range(args.repeats):
            record, output = command([str(binary), args.device], directory, f"probe-{index:02d}", 10)
            commands.append(record)
            outputs.append(output)
            if (record["returncode"] != 0 or not output.endswith(
                    "PASS: Asahi global parameters queried; values are driver-reported, no shader executed.\n")):
                return 1
        summary["repeat_stdout_identical"] = all(x == outputs[0] for x in outputs)
        summary["build_dependencies_unchanged"] = all(sha256(p) == digest for p, digest in
                                                    summary["build_dependency_sha256"].items())
        summary["passed"] = summary["repeat_stdout_identical"] and summary["build_dependencies_unchanged"]
        print(outputs[0], end="")
        return 0 if summary["passed"] else 1
    finally:
        summary["completed_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(directory / "summary.json", summary)
        print(f"{'PASS' if summary['passed'] else 'FAIL'}: {summary['scope']}")
        print(f"Run record: {directory}")


if __name__ == "__main__":
    sys.exit(main())
