#!/usr/bin/env python3
"""Independent local oracle. This report is NOT evidence of an IBM job execution."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {'LAB_ROW_ID', 'client_number', 'client_name', 'client_type', 'client_category',
          'address_line', 'city', 'postal_code', 'country', 'contact_email', 'contact_phone'}


def assess(rows):
    if not rows or any(set(r) != FIELDS for r in rows):
        raise ValueError('SCHEMA_ERROR: exact bindings required, including contact_phone')
    assert len(rows) == 200
    assert sorted(r['LAB_ROW_ID'] for r in rows) == list(range(1, 201))
    counts = Counter(r['client_number'] for r in rows if r['client_number'] is not None)
    failures = {f'BR_CLT_{i:03}': [] for i in range(1, 21)}
    evaluated = {key: 0 for key in failures}
    for row in rows:
        name, kind, category, number, address, city, postal, country, email, phone = (
            row[field] for field in ['client_name', 'client_type', 'client_category', 'client_number',
                                    'address_line', 'city', 'postal_code', 'country', 'contact_email', 'contact_phone'])
        checks = [
            (True, name is not None and bool(name.strip())),
            (name is not None, name is not None and 2 <= len(name) <= 100),
            (name is not None, bool(name) and all(unicodedata.category(c).startswith('L') or c in " '-" for c in name)),
            (True, kind is not None),
            (kind is not None, kind in ['Individual', 'Corporate', 'Government', 'Non-Profit']),
            (True, category is not None),
            (category is not None, category in ['Retail', 'SME', 'Enterprise', 'Institutional']),
            (kind == 'Individual', category == 'SME'),
            (True, number is not None),
            (number is not None, counts[number] == 1 if number is not None else False),
            (number is not None, re.fullmatch(r'[A-Z]{2}[0-9]{6}', number or '') is not None),
            (True, address is not None and bool(address.strip())),
            (address is not None, address is not None and len(address) <= 200),
            (True, city is not None),
            (postal is not None, re.fullmatch(r'[0-9]{5}', postal or '') is not None),
            (country is not None, country in ['US', 'FR', 'DE', 'GB', 'MA', 'ES', 'IT']),
            (True, email is not None),
            (email is not None, re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', email or '') is not None),
            (True, phone is not None),
            (phone is not None, re.fullmatch(r'\+[0-9]{10,15}', phone or '') is not None),
        ]
        for index, (eligible, passed) in enumerate(checks, 1):
            key = f'BR_CLT_{index:03}'
            if eligible:
                evaluated[key] += 1
                if not passed:
                    failures[key].append(row['LAB_ROW_ID'])
    return failures, evaluated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=ROOT / "local/reference-validation.json")
    args = parser.parse_args()
    baseline = json.loads((ROOT / 'data/clients-baseline.json').read_text())
    corrected = json.loads((ROOT / 'data/clients-corrected.json').read_text())
    expected = json.loads((ROOT / 'rules/expected-baseline.json').read_text())
    failures, evaluated = assess(baseline)
    assert failures == expected, {k: (failures[k], expected[k]) for k in failures if failures[k] != expected[k]}
    clean_failures, clean_evaluated = assess(corrected)
    assert all(not ids for ids in clean_failures.values())
    for name, source in [('clients-baseline', baseline), ('clients-corrected', corrected)]:
        with (ROOT / 'data' / (name + '.csv')).open(newline='', encoding='utf-8') as stream:
            decoded = [{key: int(value) if key == 'LAB_ROW_ID' else None if value == '\\N' else value
                        for key, value in row.items()} for row in csv.DictReader(stream)]
        assert decoded == source, 'CSV round trip changed null, empty, whitespace or Unicode values'
    bad_schema = [dict(r) for r in baseline]
    for row in bad_schema:
        row['contact_phone_number'] = row.pop('contact_phone')
    try:
        assess(bad_schema)
    except ValueError as error:
        schema_message = str(error)
    else:
        raise AssertionError('Missing actual phone column was accepted')
    affected = sorted(set(x for ids in failures.values() for x in ids))
    report = {'kind': 'Independent local reference verification; NOT IBM execution evidence',
              'baseline': {'clients': 200, 'rules': 20, 'violation_pairs': sum(map(len, failures.values())),
                           'affected_clients': len(affected), 'affected_row_ids': affected,
                           'failure_row_ids': failures, 'eligible_clients_by_rule': evaluated},
              'corrected': {'clients': 200, 'violation_pairs': 0, 'eligible_clients_by_rule': clean_evaluated},
              'negative_schema_probe': schema_message,
              'positive_cases': {'apostrophe_hyphen': 15, 'unicode_letter': 16},
              'assertions': 'Exact hand-authored baseline sets; clean zero; missing binding stops; 200 stable row keys; lossless CSV round trip.'}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f'LOCAL REFERENCE PASSED: {len(affected)} affected clients; {sum(map(len, failures.values()))} rule/client violation pairs; corrected=0.')


if __name__ == '__main__':
    main()
