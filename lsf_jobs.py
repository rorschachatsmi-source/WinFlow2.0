"""LSF job query / kill helpers (no GUI dependency)."""

from __future__ import annotations

import subprocess
from typing import List, Optional, Tuple

from winflow_config import get_config

# Still in the LSF queue / eligible to be killed.
ACTIVE_LSF_STATUSES = frozenset(
    {
        "PEND",
        "PSUSP",
        "RUN",
        "USUSP",
        "SSUSP",
        "WAIT",
        "PROV",
    }
)

JOB_NOT_FOUND_HINTS = (
    "not found",
    "no matching",
    "does not exist",
    "unknown job",
    "already finished",
)


def run_lsf_cmd(cmd: List[str]) -> Tuple[int, str, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except OSError as exc:
        return 1, "", str(exc)


def is_job_not_found_message(msg: str) -> bool:
    lowered = (msg or "").lower()
    return any(hint in lowered for hint in JOB_NOT_FOUND_HINTS)


def is_active_lsf_status(status: str) -> bool:
    """True for statuses that mean the job is still killable in the queue."""
    token = (status or "").strip().split()[0].upper() if status else ""
    return token in ACTIVE_LSF_STATUSES


def _bjobs_stat(job_id: str = "", lsf_name: str = "") -> str:
    """Return the LSF ``stat`` field, or empty if the job is not queryable."""
    lsf_cfg = get_config().lsf
    cmd = [lsf_cfg.bjobs]
    if lsf_cfg.bjobs_noheader:
        cmd.append("-noheader")
    cmd.extend(["-o", lsf_cfg.bjobs_output_field])
    if job_id:
        cmd.append(str(job_id))
    elif lsf_name:
        cmd.extend(["-J", lsf_name])
    else:
        return ""
    code, out, _err = run_lsf_cmd(cmd)
    if code != 0 or not out:
        return ""
    # First token of first line (handles multi-job / extra columns).
    return out.splitlines()[0].strip().split()[0]


def lsf_job_alive(job_id: str = "", lsf_name: str = "") -> bool:
    """Return True only if the job is still in an active LSF state.

    Important: LSF ``bjobs <id>`` often still returns recently finished jobs
    (DONE/EXIT). Those must not be treated as alive, or Stop will bkill them.
    """
    if job_id:
        status = _bjobs_stat(job_id=str(job_id))
        if status:
            return is_active_lsf_status(status)
    if lsf_name:
        status = _bjobs_stat(lsf_name=lsf_name)
        if status:
            return is_active_lsf_status(status)
    return False


def lsf_kill_job(job_id: str = "", lsf_name: str = "") -> Tuple[bool, str]:
    """Send bkill for a job by id (preferred) or name.

    When ``job_id`` is set, do not fall back to ``bkill -J`` — name matching
    can hit unrelated jobs.
    """
    lsf_cfg = get_config().lsf
    if job_id:
        code, out, err = run_lsf_cmd([lsf_cfg.bkill, str(job_id)])
        msg = out or err
        if code == 0:
            return True, msg
        return False, msg
    if lsf_name:
        code, out, err = run_lsf_cmd([lsf_cfg.bkill, "-J", lsf_name])
        msg = out or err
        if code == 0:
            return True, msg
        return False, msg
    return False, "No job id or name available"
