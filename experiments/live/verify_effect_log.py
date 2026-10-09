"""Reconcile the partner effect log with the consent and redelivery trials.

The partners append one line to ``EFFECT_OUTBOX`` per accepted task. That file
is append-only across sessions, so it also holds the records of the probe calls
that were made while bringing each phase up. This script partitions the log by
phase, using the caller number that the adapter embeds in the task text, and
checks the partition against the trial records:

* consent trials use ``+8800007NNN``, redelivery trials ``+8800009NNN``;
* within a phase the earliest record with index 0 is the one-trial probe that
  preceded the run, and each remaining caller index appears at most once, so a
  repeated index or a duplicated task id would mean a retry;
* a caller index that is missing from the log is a trial whose first candidate
  was not a study partner, which is what the trial record should say too.

Nothing is rewritten: the raw log is left in place and the trial-associated
records are written to a derived file for the paper.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

PHASES = {
    # caller = "+88" + f"{base + trial_index:08d}"
    "consent": {"base": 7000, "trials": "data/live_consent_execution_live.jsonl"},
    "redelivery": {"base": 9000, "trials": "data/live_consent_redelivery.jsonl"},
}
CALLER = re.compile(r"发送方号码：(\+?\d+)")


def caller_index(caller: str | None, base: int) -> int | None:
    if not caller or not caller.startswith("+88"):
        return None
    return int(caller[3:]) - base


def caller_of(record: dict) -> str | None:
    match = CALLER.search(record.get("requested_action") or "")
    return match.group(1) if match else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path,
                        default=Path("/data/caiyizhang/acps-public-demo/outbox/effects.jsonl"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("data/live_effect_reconciliation.json"))
    parser.add_argument("--trials-out", type=Path, default=Path("data/live_effects_trials.jsonl"))
    args = parser.parse_args()

    records = [json.loads(line) for line in args.log.read_text(encoding="utf-8").splitlines() if line.strip()]
    for record in records:
        record["caller"] = caller_of(record)
        record["at_iso"] = dt.datetime.fromtimestamp(record["at"]).strftime("%Y-%m-%d %H:%M:%S")

    report: dict[str, object] = {"log": str(args.log), "lines": len(records)}
    trial_records: list[dict] = []

    for phase, spec in PHASES.items():
        in_phase = [r for r in records
                    if (idx := caller_index(r["caller"], spec["base"])) is not None and 0 <= idx < 200]
        in_phase.sort(key=lambda r: r["at"])
        index0 = [r for r in in_phase if caller_index(r["caller"], spec["base"]) == 0]
        probes = index0[:1]                      # the one-trial probe ran before the batch
        trials = [r for r in in_phase if r not in probes]

        trial_rows = [json.loads(line) for line in
                      (args.data / Path(spec["trials"]).name).read_text(encoding="utf-8").splitlines() if line.strip()]
        key = "first_candidate_is_registered_partner" if phase == "consent" else "first_candidate_is_study_partner"
        expected = sum(1 for row in trial_rows if row[key])
        seen_indexes = sorted(caller_index(r["caller"], spec["base"]) for r in trials)
        task_ids = [r["task_id"] for r in in_phase]

        report[phase] = {
            "trials_in_file": len(trial_rows),
            "trials_that_selected_a_study_partner": expected,
            "probe_records": [
                {"task_id": r["task_id"], "at": r["at_iso"], "caller": r["caller"]} for r in probes
            ],
            "trial_action_records": len(trials),
            "trial_caller_indexes": seen_indexes,
            "duplicate_callers": sorted({i for i in seen_indexes if seen_indexes.count(i) > 1}),
            "duplicate_task_ids": sorted({t for t in task_ids if task_ids.count(t) > 1}),
            "missing_caller_indexes": [
                i for i in range(len(trial_rows))
                if i not in seen_indexes
            ],
            "reconciled": len(trials) == expected,
        }
        for record in trials:
            trial_records.append({**record, "phase": phase})
        print(f"{phase}: file trials={len(trial_rows)} expected actions={expected} "
              f"probe records={len(probes)} trial records={len(trials)} "
              f"missing indexes={report[phase]['missing_caller_indexes']} "
              f"reconciled={report[phase]['reconciled']}")

    report["probe_records_total"] = sum(len(report[p]["probe_records"]) for p in PHASES)
    report["trial_action_records_total"] = len(trial_records)
    report["other_records"] = [
        {"task_id": r["task_id"], "at": r["at_iso"], "note": "manual connectivity probe"}
        for r in records
        if not any((caller_index(r["caller"], s["base"]) is not None
                    and 0 <= caller_index(r["caller"], s["base"]) < 200) for s in PHASES.values())
    ]
    report["assert_lines"] = (report["trial_action_records_total"]
                              + report["probe_records_total"]
                              + len(report["other_records"]))
    assert report["assert_lines"] == report["lines"], "log partition does not add up"
    assert all(report[p]["reconciled"] for p in PHASES), "a phase does not reconcile with its trial file"
    assert not any(report[p]["duplicate_task_ids"] for p in PHASES), "duplicate task id means a retry"

    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with args.trials_out.open("w", encoding="utf-8") as handle:
        for record in trial_records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"{report['lines']} log lines = {report['trial_action_records_total']} trial actions "
          f"+ {report['probe_records_total']} phase probes + {len(report['other_records'])} manual probe(s)")
    print(f"wrote {args.out} and {args.trials_out}")


if __name__ == "__main__":
    main()
