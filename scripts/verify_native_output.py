"""Reconcile the complete IBM output with the independently authored fixture oracle.

This reads an authentic downloaded CSV. It does not execute or emulate IBM rules.
Native output has one row per evaluated definition/bound column/client; the
two-column conditional therefore has two audit rows for one business violation.
"""
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--state", choices=["baseline", "corrected"], required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--run-id", help="Select one run from an append-table export")
    parser.add_argument("--config", type=Path, default=ROOT / "local/ibm-run.json", help="Run configuration generated from your own IBM audit export")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    plan = json.loads((ROOT / "rules/native-bindings-plan.json").read_text())
    contract = json.loads((ROOT / "rules/contract.json").read_text())
    expected = json.loads((ROOT / "rules/expected-baseline.json").read_text())
    source = json.loads((ROOT / f"data/clients-{args.state}.json").read_text())
    if isinstance(source, dict):
        source = source["rows"]
    mapping = {}
    for binding in plan["bindings"]:
        for value in binding["bindings"].values():
            if "column" in value:
                key = (config["definitions"][binding["definition_key"]], value["column"])
                if key in mapping:
                    raise ValueError(f"Ambiguous binding {key}")
                mapping[key] = binding["rule_id"]
    rows = list(csv.DictReader(args.csv.open(encoding="utf-8-sig", newline="")))
    export_rows = len(rows)
    if args.run_id:
        rows = [r for r in rows if r["Job_run_ID"] == args.run_id]
    assert rows, "No audit rows found for the requested execution"
    populations, failed = defaultdict(set), defaultdict(set)
    applications = defaultdict(set)
    for row in rows:
        key = (row["Data_quality_definition_ID"], row["Bound_to_column"])
        rule = mapping[key]
        row_id = int(row["LAB_ROW_ID"])
        populations[rule].add(row_id)
        applications[rule].add(row["Disambiguator"])
        passing, failing = int(row["Passing_rules"]), int(row["Failing_rules"])
        assert passing + failing == 1, "Each audit row must describe one evaluation"
        if failing:
            failed[rule].add(row_id)
    assert {r["Rule_ID"] for r in rows} == {config["saved_rule_id"]}
    runs = {r["Job_run_ID"] for r in rows}
    assert len(runs) == 1, "Export one execution at a time"
    report_rules = []
    differences = []
    for rule in contract["rules"]:
        rid, field = rule["rule_id"], rule["field"]
        if rule["family"] == "conditional":
            eligible = {r["LAB_ROW_ID"] for r in source if r["client_type"] == "Individual"}
        elif rule["eligible_sql"] == "1=1":
            eligible = {r["LAB_ROW_ID"] for r in source}
        else:
            eligible = {r["LAB_ROW_ID"] for r in source if r[field] is not None}
        oracle = set(expected[rid]) if args.state == "baseline" else set()
        for label, actual, target in [("eligible", populations[rid], eligible),
                                      ("violations", failed[rid], oracle)]:
            if actual != target:
                differences.append({"rule": rid, "kind": label,
                                    "missing": sorted(target-actual),
                                    "unexpected": sorted(actual-target)})
        assert len(applications[rid]) == 1, "Unexpected repeated application"
        report_rules.append({"rule_id": rid, "eligible_clients": len(eligible),
                             "failed_clients": len(failed[rid]),
                             "passed_clients": len(eligible)-len(failed[rid]),
                             "failed_row_ids": sorted(failed[rid]),
                             "native_disambiguator": next(iter(applications[rid]))})
    report = {"state": args.state, "source_csv": args.csv.name,
              "sha256": hashlib.sha256(args.csv.read_bytes()).hexdigest(),
              "job_run_id": next(iter(runs)), "rule_id": config["saved_rule_id"],
              "export_rows": export_rows, "raw_audit_rows": len(rows),
              "violation_pairs": sum(len(v) for v in failed.values()),
              "affected_clients": len(set().union(*failed.values())),
              "rules": report_rules, "differences": differences,
              "exact_match": not differences}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k != "rules"}, indent=2))
    if differences:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
