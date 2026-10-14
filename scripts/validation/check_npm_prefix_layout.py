"""Offline npm CLI layout smoke: user prefix/bin must contain the command.

No package fetched: synthetic dependency-free tarball, created in a temp dir.
"""
from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path


def main() -> None:
    npm = shutil.which("npm")
    node = shutil.which("node")
    if npm is None or node is None:
        raise SystemExit("NPM_PREFIX_SMOKE=FAIL node/npm missing")
    with tempfile.TemporaryDirectory(prefix="clawfedora-npm-layout-") as directory:
        root = Path(directory)
        archive = root / "fixture.tgz"
        contents = (
            (
                "package/package.json",
                (
                    b'{"name":"clawfedora-layout-fixture","version":"1.0.0",'
                    b'"bin":{"clawfedora-layout-smoke":"bin/cli.js"}}'
                ),
                0o644,
            ),
            (
                "package/bin/cli.js",
                bytes([10]).join((
                    b"#!/usr/bin/env node",
                    b'process.stdout.write("NPM_GLOBAL_LAYOUT_OK");',
                    b"",
                )),
                0o755,
            ),
        )
        with tarfile.open(archive, "w:gz") as package:
            for name, payload, mode in contents:
                info = tarfile.TarInfo(name=name)
                info.mode = mode
                info.size = len(payload)
                package.addfile(info, io.BytesIO(payload))
        prefix = root / "prefix"
        install = subprocess.run(
            [npm, "install", "--global", "--prefix", str(prefix), "--ignore-scripts",
             "--offline", "--no-audit", "--no-fund", str(archive)],
            capture_output=True, text=True, timeout=90, check=False,
        )
        if install.returncode:
            raise SystemExit(f"NPM_PREFIX_SMOKE=FAIL install: {install.stderr[-1200:]}")
        executable = prefix / "bin" / "clawfedora-layout-smoke"
        if not executable.is_file() or not executable.is_symlink():
            raise SystemExit("NPM_PREFIX_SMOKE=FAIL CLI not linked in prefix/bin")
        check = subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=10, check=False
        )
        if check.returncode or check.stdout.strip() != "NPM_GLOBAL_LAYOUT_OK":
            raise SystemExit("NPM_PREFIX_SMOKE=FAIL executable did not start")
    print("NPM_PREFIX_SMOKE=PASS global_prefix_bin=true offline_fixture=true")


if __name__ == "__main__":
    main()
