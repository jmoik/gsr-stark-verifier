"""Macro compression and script checks with the `gsr` command of gsr-tooling, pinned to the revision these scripts
were measured with.

Install it with

    cargo install --locked --git https://github.com/bitcoin-gsr/gsr-tooling --rev 04cda8374cef2ad05d9f90c67d7eb8e52ee47ba1

or set `GSR` to a `gsr` binary. The compressed scripts, and so the covenant and rollup addresses, depend on the
revision.
"""
import json
import os
import shutil
import subprocess

REPOSITORY = "https://github.com/bitcoin-gsr/gsr-tooling"
REVISION = "04cda8374cef2ad05d9f90c67d7eb8e52ee47ba1"


def run(*args: str, script: bytes) -> subprocess.CompletedProcess:
    gsr = os.environ.get("GSR") or shutil.which("gsr")
    if not gsr:
        raise RuntimeError(f"gsr not found: cargo install --locked --git {REPOSITORY} --rev {REVISION}, or set GSR")
    return subprocess.run([gsr, *args], input=script.hex(), capture_output=True, text=True)


def compress(script: bytes, protect: tuple[int, int] = (0, 0)) -> tuple[bytes, dict]:
    """-> (compressed script, `gsr compress` summary). The result unrolls to exactly `script` and passes `check`.
    The main-script byte range `protect`, which must start at 0 (the rollup leaf's head and prologue), stays literal
    at its offsets, and the result does not depend on its values."""
    assert protect[0] == 0, "a protected range must start the main script"
    p = run("compress", "--protect", str(protect[1]), script=script)
    if p.returncode:
        raise RuntimeError(p.stderr.strip())
    code = bytes.fromhex(p.stdout.strip())
    check(code)
    return code, json.loads(p.stderr)


def check(script: bytes) -> dict:
    """The `gsr check` report (consensus errors, policy warnings and lints, without executing the script); raises if
    it has errors, such as an OP_SUCCESSx, a malformed macro or an unrolled script over the size limit."""
    p = run("check", "--json", script=script)
    try:
        report = json.loads(p.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip()) from None
    if report["errors"]:
        raise RuntimeError("gsr check: " + "; ".join(f"{d['rule']} at byte {d['offset']}: {d['message']}"
                                                     for d in report["diagnostics"] if d["severity"] == "error"))
    return report
