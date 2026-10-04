"""Collect reproducibility metadata without opening a DRM device."""

import hashlib
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys


def text_file(path):
    try:
        return Path(path).read_text(errors="replace").replace("\0", "\n").strip()
    except OSError:
        return None


def command_output(argv, cwd):
    try:
        result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=10)
        return {"argv": argv, "returncode": result.returncode,
                "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"argv": argv, "error": str(error)}


def sha256(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def collect(repo):
    nodes = []
    for path in sorted(Path("/dev/dri").glob("*")):
        try:
            info = path.stat()
            nodes.append({"path": str(path), "mode": stat.filemode(info.st_mode),
                          "major": os.major(info.st_rdev), "minor": os.minor(info.st_rdev),
                          "read_write_access": os.access(path, os.R_OK | os.W_OK),
                          "sysfs_path": str((Path("/sys/class/drm") / path.name).resolve())})
        except OSError as error:
            nodes.append({"path": str(path), "error": str(error)})

    headers = ["/usr/include/drm/drm.h", "/usr/include/drm/asahi_drm.h"]
    return {
        "kernel": {"system": platform.system(), "release": platform.release(),
                   "version": platform.version(), "machine": platform.machine()},
        "os_release": text_file("/etc/os-release"),
        "python": sys.version,
        "container_marker_present": Path("/.dockerenv").exists(),
        "device_tree_model": text_file("/proc/device-tree/model"),
        "device_tree_compatible": text_file("/proc/device-tree/compatible"),
        "drm_nodes": nodes,
        "headers": {path: sha256(path) for path in headers},
        "tools": {name: shutil.which(name) for name in
                  ("cc", "make", "pkg-config", "vulkaninfo", "clinfo",
                   "glslangValidator", "spirv-as", "xcrun")},
        "git_head": command_output(["git", "rev-parse", "HEAD"], repo),
        "git_status": command_output(["git", "status", "--porcelain"], repo),
        "libdrm_pkg_config": command_output(["pkg-config", "--modversion", "libdrm"], repo),
    }
