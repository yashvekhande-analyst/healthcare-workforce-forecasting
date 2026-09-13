import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from .config import read_config, paths, save_json


def parser():
    p = argparse.ArgumentParser(description="Historical replay of nursing-home contract staffing utilization")
    p.add_argument("--config", default="configs/full.json", help="JSON profile; includes state, dates, facilities and split cutoffs")
    sub = p.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--national-csv", action="store_true")
    m = sub.add_parser("ingest-manual")
    m.add_argument("file")
    m.add_argument("--period", required=True, help="YYYY-MM-DD/YYYY-MM-DD")
    m.add_argument("--source-url", required=True)
    for name in ("prepare", "train", "backtest", "report", "run"):
        sub.add_parser(name)
    pr = sub.add_parser("predict")
    pr.add_argument("--origin", required=True)
    re = sub.add_parser("realize")
    re.add_argument("--asof", required=True)
    mo = sub.add_parser("monitor")
    mo.add_argument("--asof", required=True)
    mo.add_argument("--demo-alert", action="store_true")
    return p


def execute(c, args):
    from .ingest import fetch, manual
    from .prepare import prepare
    from .modeling import train, backtest
    from .predict import predict, realize
    from .monitoring import monitor
    command = args.command
    if command == "fetch":
        m = fetch(c["root"], c["start"], c["end"], c["state"], args.national_csv)
        return {"registered_files": len(m["files"])}
    if command == "ingest-manual":
        return manual(c["root"], args.file, args.period, source_url=args.source_url)
    if command == "prepare":
        return prepare(c)
    if command == "train":
        return train(c)
    if command == "backtest":
        return backtest(c)
    if command == "predict":
        return predict(c, args.origin)
    if command == "realize":
        return realize(c, args.asof)
    if command == "monitor":
        return monitor(c, args.asof, args.demo_alert)
    if command == "report":
        from .reporting import reports
        return reports(c)
    if command == "run":
        from .reporting import reports
        prepare(c)
        train(c)
        backtest(c)
        predict(c, c["test"][1])
        predict(c, c["end"])
        realize(c, c["end"])
        monitor(c, c["end"])
        monitor(c, c["end"], scenario=True)
        return reports(c)


def main():
    args = parser().parse_args()
    c = read_config(args.config)
    _, run = paths(c)
    status_path = run / "job_status.json"
    statuses = json.loads(status_path.read_text()) if status_path.exists() else {}
    job = {"started_at": datetime.now(timezone.utc).isoformat(), "status": "running"}
    statuses[args.command] = job
    save_json(status_path, statuses)
    try:
        result = execute(c, args)
        job.update(status="success", ended_at=datetime.now(timezone.utc).isoformat())
        print(json.dumps(result, indent=2, default=str, allow_nan=False))
    except Exception as exc:
        job.update(status="failed", error=str(exc), ended_at=datetime.now(timezone.utc).isoformat())
        traceback.print_exc()
        sys.exit(1)
    finally:
        save_json(status_path, statuses)
        with (run / "jobs.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"command": args.command, **job}) + "\n")


if __name__ == "__main__":
    main()
