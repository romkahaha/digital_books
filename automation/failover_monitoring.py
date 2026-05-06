"""Monitoring failover bundle sync + GitHub Actions request runner."""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from automation.config import load_json_config, monitoring_defaults, path_from_config
from automation.listing_enrichment import load_items_py
from automation.monitoring.send_telegram_alerts import alert_state_path_from
from automation.risk_filters import repo_root_from
from automation.state import items_signature


REQUEST_REL = Path("automation_runtime/failover_request_latest.json")
FAILOVER_CONFIG_REL = Path("automation/configs/monitoring_failover.json")
WORKFLOW_REL = Path(".github/workflows/monitoring_failover.yml")
STATE_REL = Path("automation_runtime/state.json")
ALERT_STATE_REL = Path("automation_runtime/state_telegram_alerts.json")

SYNC_FILES = (
    Path("requirements.txt"),
    Path("automation_runtime/monitor_list_latest.py"),
    Path("automation_runtime/monitor_list_latest.csv"),
    Path("automation_runtime/base_snapshot_latest.csv"),
    Path("automation_runtime/risk_metrics_latest.csv"),
    STATE_REL,
    ALERT_STATE_REL,
    Path("steam_listings/data/float_fit_rel_curves.json"),
)
SYNC_DIRS = (
    Path("automation"),
    Path("steam_listings"),
)
SYNC_OPTIONAL_DIRS = (
    Path("automation_runtime/precomputed_fit_plots/skins_normal_filtered1"),
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


@dataclass(frozen=True)
class FailoverConfig:
    enabled: bool
    repo_path: Path | None
    remote_url: str
    branch: str
    push_on_cycle_start: bool
    request_on_rate_limit: bool
    lease_seconds: int
    copy_precomputed_plots: bool


def derive_failover_lease_seconds(config: dict[str, Any]) -> int:
    cycle_cfg = config.get("cycle", {})
    raw = cycle_cfg.get("recoverable_error_sleep_sec", cycle_cfg.get("cycle_sleep_sec", 5400))
    try:
        value = int(float(raw))
    except Exception:
        value = 5400
    return max(60, value)


def parse_args() -> argparse.Namespace:
    root = repo_root_from(Path(__file__))
    parser = argparse.ArgumentParser(description="Sync and run monitoring failover bundles.")
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync", help="Sync current monitoring inputs/state to failover repo.")
    sync.add_argument("--config", type=Path, default=root / "automation" / "configs" / "monitoring.json")
    sync.add_argument("--mode", choices=["standby", "request", "clear"], required=True)
    sync.add_argument("--lease-seconds", type=int, default=None)
    sync.add_argument("--reason", type=str, default="")
    sync.add_argument("--batch-pointer", type=int, default=None)
    sync.add_argument("--state-json", type=Path, default=None)
    sync.add_argument("--monitor-items-py", type=Path, default=None)

    run_req = sub.add_parser("run-request", help="Run failover monitoring request inside failover repo.")
    run_req.add_argument("--request-json", type=Path, default=REQUEST_REL)
    run_req.add_argument("--config", type=Path, default=FAILOVER_CONFIG_REL)
    run_req.add_argument("--root", type=Path, default=root)
    return parser.parse_args()


def load_failover_config(config: dict[str, Any], repo_root: Path) -> FailoverConfig:
    cfg = config.get("failover", {})
    repo_path_raw = cfg.get("repo_path")
    repo_path = None
    if repo_path_raw:
        repo_path = Path(str(repo_path_raw)).expanduser()
        if not repo_path.is_absolute():
            repo_path = (repo_root / repo_path).resolve()
    return FailoverConfig(
        enabled=bool(cfg.get("enabled", False)),
        repo_path=repo_path,
        remote_url=str(cfg.get("remote_url", "")).strip(),
        branch=str(cfg.get("branch", "main")).strip() or "main",
        push_on_cycle_start=bool(cfg.get("push_on_cycle_start", True)),
        request_on_rate_limit=bool(cfg.get("request_on_rate_limit", True)),
        lease_seconds=derive_failover_lease_seconds(config),
        copy_precomputed_plots=bool(cfg.get("copy_precomputed_plots", True)),
    )


def run_git(repo: Path, args: list[str], *, check: bool = True, capture_output: bool = False) -> subprocess.CompletedProcess:
    cmd = ["git", "-C", str(repo), *args]
    return subprocess.run(cmd, check=check, text=True, capture_output=capture_output)


def ensure_failover_repo(cfg: FailoverConfig) -> Path:
    if not cfg.enabled:
        raise RuntimeError("failover is disabled in monitoring config")
    if cfg.repo_path is None:
        raise RuntimeError("failover.repo_path is not configured")
    repo = cfg.repo_path
    if not (repo / ".git").is_dir():
        raise RuntimeError(f"failover repo is not a git checkout: {repo}")
    if cfg.remote_url:
        remotes = run_git(repo, ["remote", "-v"], capture_output=True).stdout
        if "origin" not in remotes:
            run_git(repo, ["remote", "add", "origin", cfg.remote_url])
        elif cfg.remote_url not in remotes:
            print(f"warning: failover repo origin differs from configured remote_url ({cfg.remote_url})", file=sys.stderr)
    return repo


def copy_file(src_root: Path, dst_root: Path, rel: Path) -> bool:
    src = src_root / rel
    if not src.exists():
        return False
    dst = dst_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def copy_tree(src_root: Path, dst_root: Path, rel: Path) -> bool:
    src = src_root / rel
    if not src.exists():
        return False
    dst = dst_root / rel
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store"),
    )
    return True


def sent_alerts_count(state_json: Path) -> int:
    if not state_json.is_file():
        return 0
    try:
        payload = json.loads(state_json.read_text(encoding="utf-8"))
    except Exception:
        return 0
    sent = payload.get("sent_alerts")
    return len(sent) if isinstance(sent, dict) else 0


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_iso_datetime(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except Exception:
        return None


def payload_timestamp(payload: dict[str, Any]) -> datetime | None:
    for key in (
        "last_finished_at_utc",
        "last_run_at_utc",
        "completed_at_utc",
        "last_failover_completed_at_utc",
    ):
        dt = parse_iso_datetime(payload.get(key))
        if dt is not None:
            return dt
    return None


def same_items_signature(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_sig = str(left.get("items_signature") or "").strip()
    right_sig = str(right.get("items_signature") or "").strip()
    return bool(left_sig and right_sig and left_sig == right_sig)


def merge_sent_alerts(
    current: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> tuple[dict[str, Any], bool]:
    merged = dict(current) if isinstance(current, dict) else {}
    changed = False
    incoming = incoming if isinstance(incoming, dict) else {}
    for key, value in incoming.items():
        if key not in merged:
            merged[key] = value
            changed = True
            continue
        existing = merged.get(key)
        if not isinstance(existing, dict) or not isinstance(value, dict):
            continue
        existing_dt = parse_iso_datetime(existing.get("sent_at_utc"))
        incoming_dt = parse_iso_datetime(value.get("sent_at_utc"))
        if incoming_dt and (existing_dt is None or incoming_dt > existing_dt):
            merged[key] = value
            changed = True
    return merged, changed


def maybe_pull_failover_repo(repo: Path, branch: str) -> None:
    remotes = {line.strip() for line in run_git(repo, ["remote"], capture_output=True).stdout.splitlines() if line.strip()}
    if "origin" not in remotes:
        return
    run_git(repo, ["pull", "--ff-only", "origin", branch])


def import_runtime_state_from_failover(
    *,
    repo_root: Path,
    config: dict[str, Any],
    quiet: bool = False,
) -> bool:
    failover_cfg = load_failover_config(config, repo_root)
    if not failover_cfg.enabled:
        return False
    repo = ensure_failover_repo(failover_cfg)
    try:
        maybe_pull_failover_repo(repo, failover_cfg.branch)
    except Exception as exc:
        if not quiet:
            print(f"warning: failover repo pull failed before runtime import: {exc}", file=sys.stderr, flush=True)

    main_state_path = path_from_config(config, "state_json")
    main_alert_state_path = alert_state_path_from(main_state_path)
    failover_state_path = repo / STATE_REL
    failover_alert_state_path = repo / ALERT_STATE_REL

    main_state = load_json_object(main_state_path)
    failover_state = load_json_object(failover_state_path)
    main_alert_state = load_json_object(main_alert_state_path)
    failover_alert_state = load_json_object(failover_alert_state_path)

    changed = False

    if failover_state and (
        not main_state
        or same_items_signature(main_state, failover_state)
        or not str(main_state.get("items_signature") or "").strip()
    ):
        main_ts = payload_timestamp(main_state) if main_state else None
        failover_ts = payload_timestamp(failover_state)
        if failover_ts and (main_ts is None or failover_ts > main_ts):
            write_json(main_state_path, failover_state)
            main_state = failover_state
            changed = True
            if not quiet:
                print(
                    "imported newer failover monitoring state "
                    f"(batch_pointer={failover_state.get('batch_pointer')})",
                    flush=True,
                )

    if failover_alert_state and (
        not main_alert_state
        or same_items_signature(main_alert_state, failover_alert_state)
        or not str(main_alert_state.get("items_signature") or "").strip()
    ):
        base = copy.deepcopy(main_alert_state or failover_alert_state)
        remote_is_newer = False
        base_ts = payload_timestamp(main_alert_state) if main_alert_state else None
        failover_alert_ts = payload_timestamp(failover_alert_state)
        if failover_alert_ts and (base_ts is None or failover_alert_ts > base_ts):
            base = copy.deepcopy(failover_alert_state)
            remote_is_newer = True
        merged_sent, merged_changed = merge_sent_alerts(
            main_alert_state.get("sent_alerts") if main_alert_state else {},
            failover_alert_state.get("sent_alerts"),
        )
        if merged_changed or remote_is_newer or not main_alert_state:
            base["sent_alerts"] = merged_sent
            write_json(main_alert_state_path, base)
            changed = True
            if not quiet:
                print(
                    "merged failover Telegram dedupe state "
                    f"(sent_alerts={len(merged_sent)})",
                    flush=True,
                )

    return changed


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def workflow_text() -> str:
    return """name: Monitoring Failover

on:
  push:
    branches:
      - main
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: monitoring-failover
  cancel-in-progress: false

jobs:
  run-failover:
    runs-on: ubuntu-latest
    timeout-minutes: 120
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Check failover request
        id: request
        run: |
          python - <<'PY'
          import json
          import os
          from pathlib import Path
          request_path = Path("automation_runtime/failover_request_latest.json")
          active = "false"
          mode = "missing"
          if request_path.is_file():
              payload = json.loads(request_path.read_text(encoding="utf-8"))
              mode = str(payload.get("mode", "unknown"))
              active = "true" if payload.get("trigger_run") else "false"
          with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
              handle.write(f"active={active}\\n")
              handle.write(f"mode={mode}\\n")
          print(f"failover request mode={mode} active={active}")
          PY

      - name: Install dependencies
        if: steps.request.outputs.active == 'true'
        run: |
          python -m pip install --upgrade pip
          python -m pip install -r requirements.txt

      - name: Run monitoring failover request
        if: steps.request.outputs.active == 'true'
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TG_BOT_TOKEN: ${{ secrets.TG_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          TG_CHAT_ID: ${{ secrets.TG_CHAT_ID }}
        run: |
          python automation/failover_monitoring.py run-request
"""


def build_failover_config(config: dict[str, Any], *, lease_seconds: int) -> dict[str, Any]:
    out = copy.deepcopy(config)
    out.setdefault("schedule", {})
    out["schedule"]["enabled"] = False
    out["schedule"]["enforce_active_window"] = False
    out.setdefault("cycle", {})
    out["cycle"]["commit_runtime"] = False
    out["cycle"]["respect_active_window"] = False
    out["cycle"]["max_runtime_minutes"] = max(1.0, lease_seconds / 60.0)
    out.setdefault("telegram", {})
    out["telegram"]["enabled"] = False
    out["failover"] = {"enabled": False}
    return out


def build_request_payload(
    *,
    repo_root: Path,
    mode: str,
    lease_seconds: int,
    reason: str,
    state_path: Path,
    items: list[str],
    batch_pointer: int | None,
) -> dict[str, Any]:
    request_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{platform.node()}-{mode}"
    cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=int(lease_seconds))
    alert_state_path = alert_state_path_from(state_path)
    try:
        state_payload = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    except Exception:
        state_payload = {}
    return {
        "version": 1,
        "mode": mode,
        "request_id": request_id,
        "requested_at_utc": utc_now_iso(),
        "requested_by": platform.node(),
        "main_repo_root": str(repo_root),
        "trigger_run": mode == "request",
        "lease_seconds": int(lease_seconds),
        "max_runtime_minutes": max(1, math.ceil(lease_seconds / 60.0)),
        "cooldown_until_utc": cooldown_until.isoformat(),
        "reason": reason,
        "batch_pointer": batch_pointer,
        "items_count": len(items),
        "items_signature": items_signature(items),
        "sent_alerts_count": sent_alerts_count(alert_state_path),
        "last_status": state_payload.get("last_status"),
        "last_error": state_payload.get("last_error"),
        "last_finished_at_utc": state_payload.get("last_finished_at_utc"),
        "last_successful_monitoring_at_utc": state_payload.get("last_successful_monitoring_at_utc"),
    }


def sync_monitoring_failover(
    *,
    repo_root: Path,
    config_path: Path,
    config: dict[str, Any],
    mode: str,
    reason: str = "",
    lease_seconds: int | None = None,
    state_path: Path | None = None,
    monitor_items_py: Path | None = None,
    batch_pointer: int | None = None,
) -> bool:
    failover_cfg = load_failover_config(config, repo_root)
    if not failover_cfg.enabled:
        return False
    repo = ensure_failover_repo(failover_cfg)
    import_runtime_state_from_failover(repo_root=repo_root, config=config, quiet=True)

    state_path = state_path or Path(str(config["paths"]["state_json"])).resolve()
    monitor_items_py = monitor_items_py or Path(str(config["paths"]["monitor_items_py"])).resolve()
    items = load_items_py(monitor_items_py)
    lease = int(lease_seconds if lease_seconds is not None else failover_cfg.lease_seconds)

    copied_any = False
    for rel in SYNC_DIRS:
        copied_any = copy_tree(repo_root, repo, rel) or copied_any
    for rel in SYNC_FILES:
        copied_any = copy_file(repo_root, repo, rel) or copied_any
    if failover_cfg.copy_precomputed_plots:
        for rel in SYNC_OPTIONAL_DIRS:
            copied_any = copy_tree(repo_root, repo, rel) or copied_any

    request_payload = build_request_payload(
        repo_root=repo_root,
        mode=mode,
        lease_seconds=lease,
        reason=reason,
        state_path=state_path,
        items=items,
        batch_pointer=batch_pointer,
    )
    write_json(repo / REQUEST_REL, request_payload)
    write_json(repo / FAILOVER_CONFIG_REL, build_failover_config(config, lease_seconds=lease))
    workflow_path = repo / WORKFLOW_REL
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(workflow_text(), encoding="utf-8")

    run_git(repo, ["add", "."])
    diff = subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        print(f"failover sync ({mode}): no changes to commit")
        return copied_any
    if diff.returncode != 1:
        raise RuntimeError(f"failover git diff failed with exit {diff.returncode}")

    message = {
        "standby": "Sync monitoring failover standby bundle",
        "request": "Request monitoring failover run",
        "clear": "Clear monitoring failover request",
    }.get(mode, f"Update monitoring failover ({mode})")
    run_git(repo, ["commit", "-m", message])
    remotes = {line.strip() for line in run_git(repo, ["remote"], capture_output=True).stdout.splitlines() if line.strip()}
    if "origin" not in remotes:
        print(f"failover sync ({mode}): committed locally (origin remote is not configured yet)")
        return True
    run_git(repo, ["push", "origin", f"HEAD:{failover_cfg.branch}"])
    print(f"failover sync ({mode}): committed and pushed to {failover_cfg.branch}")
    return True


def load_request(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"failover request file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def finalize_request_payload(request: dict[str, Any], *, exit_code: int) -> dict[str, Any]:
    payload = copy.deepcopy(request)
    payload["trigger_run"] = False
    payload["mode"] = "clear"
    payload["last_failover_status"] = "success" if exit_code == 0 else "error"
    payload["last_failover_exit_code"] = int(exit_code)
    payload["last_failover_completed_at_utc"] = utc_now_iso()
    return payload


def push_failover_runtime(repo_root: Path, *, branch: str) -> bool:
    run_git(repo_root, ["config", "user.name", "github-actions[bot]"])
    run_git(repo_root, ["config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
    run_git(
        repo_root,
        [
            "add",
            str(STATE_REL),
            str(ALERT_STATE_REL),
            str(REQUEST_REL),
        ],
    )
    diff = subprocess.run(["git", "-C", str(repo_root), "diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        print("failover runtime sync-back: no state changes to commit")
        return False
    if diff.returncode != 1:
        raise RuntimeError(f"failover runtime diff failed with exit {diff.returncode}")
    run_git(repo_root, ["commit", "-m", "Update monitoring failover runtime [skip ci]"])
    remotes = {line.strip() for line in run_git(repo_root, ["remote"], capture_output=True).stdout.splitlines() if line.strip()}
    if "origin" not in remotes:
        print("failover runtime sync-back: committed locally (origin remote is not configured)")
        return True
    run_git(repo_root, ["push", "origin", f"HEAD:{branch}"])
    print(f"failover runtime sync-back: committed and pushed to {branch}")
    return True


def run_failover_request(*, repo_root: Path, request_json: Path, config_path: Path) -> int:
    request = load_request(request_json)
    if not bool(request.get("trigger_run")):
        print(f"failover request inactive (mode={request.get('mode')}); nothing to do")
        return 0
    lease_seconds = max(60, int(request.get("lease_seconds") or 5400))
    max_runtime_minutes = max(1, int(math.ceil(lease_seconds / 60.0)))
    cmd = [
        sys.executable,
        "-B",
        str(repo_root / "automation" / "monitoring" / "run_cycle.py"),
        "--config",
        str(config_path),
        "--send-telegram",
        "--ignore-schedule",
        "--no-git",
        "--max-runtime-minutes",
        str(max_runtime_minutes),
    ]
    print(f"starting failover monitoring request {request.get('request_id')} lease={lease_seconds}s")
    print(" ".join(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=str(repo_root))
    exit_code = int(completed.returncode)
    finalized_request = finalize_request_payload(request, exit_code=exit_code)
    write_json(request_json, finalized_request)
    branch = str(os.environ.get("GITHUB_REF_NAME") or "main").strip() or "main"
    push_failover_runtime(repo_root, branch=branch)
    return exit_code


def main() -> int:
    configure_stdio()
    args = parse_args()
    if args.command == "sync":
        repo_root = repo_root_from(Path(__file__))
        config_path = args.config.resolve()
        config = load_json_config(config_path, monitoring_defaults())
        state_path = args.state_json.resolve() if args.state_json else path_from_config(config, "state_json")
        monitor_items_py = (
            args.monitor_items_py.resolve() if args.monitor_items_py else path_from_config(config, "monitor_items_py")
        )
        sync_monitoring_failover(
            repo_root=repo_root,
            config_path=config_path,
            config=config,
            mode=args.mode,
            reason=args.reason,
            lease_seconds=args.lease_seconds,
            state_path=state_path,
            monitor_items_py=monitor_items_py,
            batch_pointer=args.batch_pointer,
        )
        return 0

    if args.command == "run-request":
        repo_root = args.root.resolve()
        return run_failover_request(
            repo_root=repo_root,
            request_json=args.request_json.resolve(),
            config_path=args.config.resolve(),
        )

    raise RuntimeError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
