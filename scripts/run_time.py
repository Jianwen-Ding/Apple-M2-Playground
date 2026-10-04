"""Bounded read-only Asahi GET_TIME probe; builds/logs live in scratch."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile

from collect_environment import collect, sha256
from run import REPO, logged_command, write_json


def analyze(rows, expected_count=None, expected_interval=None):
    """Reject incomplete/malformed probe output before computing diagnostics."""
    if not rows or any(not isinstance(r, dict) for r in rows):
        raise ValueError("expected nonempty JSON object records")
    metadata = rows[0]
    if metadata.get("kind") != "metadata" or any(r.get("kind") != "sample" for r in rows[1:]):
        raise ValueError("expected one metadata record followed by samples")
    count = metadata.get("samples")
    interval = metadata.get("interval_ms")
    if (type(count) is not int or not 2 <= count <= 256 or
            type(interval) is not int or not 0 <= interval <= 20 or
            metadata.get("driver") != "asahi" or
            metadata.get("host_clock") != "CLOCK_MONOTONIC_RAW" or
            metadata.get("uapi_units") != "nanoseconds" or
            metadata.get("struct_size") != 16):
        raise ValueError("invalid probe metadata")
    if ((expected_count is not None and count != expected_count) or
            (expected_interval is not None and interval != expected_interval)):
        raise ValueError("metadata does not match requested phase")
    samples = rows[1:]
    if len(samples) != count:
        raise ValueError(f"expected {count} successful samples, got {len(samples)}")
    fields = ("index", "host_before_ns", "host_after_ns", "flags",
              "gpu_timestamp_ns", "returncode", "errno")
    for index, sample in enumerate(samples):
        if any(type(sample.get(k)) is not int or not 0 <= sample[k] < 2**64 for k in fields):
            raise ValueError(f"sample {index}: missing or invalid integer field")
        if (sample["index"] != index or sample["returncode"] != 0 or
                sample["errno"] != 0 or sample["flags"] != 0):
            raise ValueError(f"sample {index}: unsuccessful or out-of-order sample")
        if sample["host_after_ns"] < sample["host_before_ns"]:
            raise ValueError(f"sample {index}: reversed host bracket")
        if index and sample["host_before_ns"] < samples[index - 1]["host_after_ns"]:
            raise ValueError(f"sample {index}: overlapping or backward host brackets")
    deltas = [b["gpu_timestamp_ns"] - a["gpu_timestamp_ns"]
              for a, b in zip(samples, samples[1:])]
    first, last = samples[0], samples[-1]
    gpu_delta = last["gpu_timestamp_ns"] - first["gpu_timestamp_ns"]
    lower = last["host_before_ns"] - first["host_after_ns"]
    upper = last["host_after_ns"] - first["host_before_ns"]
    mid = (lower + upper) / 2
    if mid <= 0 or gpu_delta <= 0:
        raise ValueError("nonpositive host or returned elapsed time")
    widths = [s["host_after_ns"] - s["host_before_ns"] for s in samples]
    return {"successful_samples": len(samples), "expected_samples": count,
            "backward_steps": sum(d < 0 for d in deltas),
            "equal_steps": deltas.count(0), "min_delta_ns": min(deltas),
            "max_delta_ns": max(deltas), "gpu_elapsed_ns": gpu_delta,
            "host_elapsed_bounds_ns": [lower, upper], "gpu_ns_per_host_ns": gpu_delta / mid,
            "ratio_bracket": [gpu_delta / upper, gpu_delta / lower] if lower > 0 else None,
            "host_ioctl_bracket_ns": {"min": min(widths), "max": max(widths)},
            "scope": "UAPI nanoseconds vs host raw clock; brackets do not measure ISA latency."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="/dev/dri/renderD128")
    parser.add_argument("--scratch-root", type=Path, default=Path("/scratch/apple-m2-playground"))
    args = parser.parse_args()
    root = args.scratch_root.resolve() / "runs"
    root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-driver-time-"), dir=root))
    write_json(directory / "environment.json", collect(REPO))
    summary = {"device": args.device, "source_sha256": {
        str(p.relative_to(REPO)): sha256(p) for p in
        [REPO / "tests/drm_time.c", REPO / "scripts/run_time.py", REPO / "scripts/run.py", REPO / "scripts/collect_environment.py"]},
        "commands": [], "analyses": {}, "passed": False,
        "scope": "Read-only DRM VERSION and GET_TIME; no shaders or resets."}
    binary = directory / "drm_time"
    result = logged_command(shlex.split(os.environ.get("CC", "cc")) +
                            ["-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
                             "tests/drm_time.c", "-o", str(binary)], directory, "compile", 60)
    summary["commands"].append(result)
    if result["returncode"] == 0:
        for label, count, interval in [("warmup", 8, 0), ("burst", 128, 0),
                                       ("paced", 64, 10), ("paced_repeat", 64, 10)]:
            result = logged_command([str(binary), args.device, str(count), str(interval)], directory, label, 10)
            summary["commands"].append(result)
            if result["returncode"] != 0:
                summary["analyses"][label] = {"error": "probe command failed"}
                break
            try:
                rows = [json.loads(line) for line in
                        (directory / f"{label}.stdout.txt").read_text().splitlines()]
                analysis = analyze(rows, count, interval)
            except (ValueError, TypeError) as error:
                summary["analyses"][label] = {"error": str(error)}
                break
            summary["analyses"][label] = analysis
            if analysis["backward_steps"]:
                break
        else:
            summary["passed"] = True
    write_json(directory / "summary.json", summary)
    print(f"{'PASS' if summary['passed'] else 'FAIL'}: {summary['scope']}")
    print(f"Run record: {directory}")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
