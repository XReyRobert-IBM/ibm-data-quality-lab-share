"""Prepare local Db2 files and discover this reader's IDs from an IBM audit export."""
import argparse
import csv
import json
from pathlib import Path
import re
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]


def discover_run(path, requested_run):
    definitions = json.loads((ROOT/'rules/native-definitions.json').read_text())['definitions']
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    required = {'Data_quality_definition', 'Data_quality_definition_ID', 'Rule_ID', 'Job_run_ID'}
    if not rows or not required <= rows[0].keys():
        raise ValueError('Export the native audit with definition name/ID, Rule ID and Job run ID.')
    if requested_run:
        rows = [row for row in rows if row['Job_run_ID']==requested_run]
    if not rows:
        raise ValueError('No audit rows for the requested run.')
    runs = {row['Job_run_ID'] for row in rows}
    rules = {row['Rule_ID'] for row in rows}
    if len(runs)!=1 or len(rules)!=1:
        raise ValueError('Select one portfolio execution with --run-id.')
    mapping = {}
    expected_names = {item['name'] for item in definitions}
    if {row['Data_quality_definition'] for row in rows} != expected_names:
        raise ValueError('The export must contain the nine definitions with the supplied names.')
    for item in definitions:
        ids = {row['Data_quality_definition_ID'] for row in rows
               if row['Data_quality_definition']==item['name']}
        if len(ids)!=1:
            raise ValueError('A definition name maps to several IDs; use an isolated lab portfolio.')
        mapping[item['key']] = ids.pop()
    if len(set(mapping.values()))!=len(definitions):
        raise ValueError('The nine definitions must have distinct IDs.')
    for value in [*mapping.values(), *runs, *rules]:
        UUID(value)
    return {'saved_rule_id':rules.pop(), 'reference_run_id':runs.pop(), 'definitions':mapping}


def native_report(schema, config):
    plan = json.loads((ROOT/'rules/native-bindings-plan.json').read_text())['bindings']
    contract = json.loads((ROOT/'rules/contract.json').read_text())
    fields = {rule['rule_id']:rule['field'] for rule in contract['rules']}
    metadata = []
    for binding in plan:
        definition = config['definitions'][binding['definition_key']]
        for value in binding['bindings'].values():
            if 'column' in value:
                metadata.append((definition,value['column'],binding['rule_id'],fields[binding['rule_id']]))
    if len({row[:2] for row in metadata})!=len(metadata):
        raise ValueError('Ambiguous definition/column mapping.')
    def literal(value):
        return "'"+value.replace("'","''")+"'"
    values=',\n    '.join('('+', '.join(map(literal,row))+')' for row in metadata)
    observed='\n      '.join(f'WHEN {literal(field)} THEN A."{field}"' for field in sorted(set(fields.values())))
    return f'''-- IDs discovered from your own audit export; no original-project disambiguators.
-- The two bound columns of the condition are deduplicated per requirement/client/run.
CREATE OR REPLACE VIEW {schema}.DQ_V2_NATIVE_RESULTS_20261015 AS
WITH M(DEFINITION_ID, BOUND_COLUMN, BUSINESS_RULE_ID, FIELD_NAME) AS (VALUES
    {values}
)
SELECT DISTINCT M.BUSINESS_RULE_ID, A."LAB_ROW_ID" AS LAB_ROW_ID, M.FIELD_NAME,
  CAST(CASE M.FIELD_NAME
      {observed}
  END AS VARCHAR(512)) AS OBSERVED_VALUE,
  A."Data_quality_definition_ID" AS DEFINITION_ID,
  A."Failing_rules" AS FAILED, A."Job_run_ID" AS JOB_RUN_ID,
  A."Rule_ID" AS PORTFOLIO_RULE_ID
FROM {schema}.DQ_V2_NATIVE_AUDIT_20261015 A
JOIN M
ON A."Data_quality_definition_ID"=M.DEFINITION_ID AND A."Bound_to_column"=M.BOUND_COLUMN
WHERE A."Rule_ID"={literal(config['saved_rule_id'])};

SELECT JOB_RUN_ID, BUSINESS_RULE_ID, COUNT(*) AS EVALUATED_CLIENTS,
  SUM(FAILED) AS FAILED_CLIENTS, COUNT(*)-SUM(FAILED) AS PASSED_CLIENTS
FROM {schema}.DQ_V2_NATIVE_RESULTS_20261015
GROUP BY JOB_RUN_ID, BUSINESS_RULE_ID ORDER BY JOB_RUN_ID, BUSINESS_RULE_ID;

SELECT JOB_RUN_ID, SUM(FAILED) AS RULE_CLIENT_VIOLATIONS,
  COUNT(DISTINCT CASE WHEN FAILED=1 THEN LAB_ROW_ID END) AS AFFECTED_CLIENTS
FROM {schema}.DQ_V2_NATIVE_RESULTS_20261015 GROUP BY JOB_RUN_ID;

SELECT BUSINESS_RULE_ID, LAB_ROW_ID, FIELD_NAME, OBSERVED_VALUE,
  DEFINITION_ID, JOB_RUN_ID, PORTFOLIO_RULE_ID
FROM {schema}.DQ_V2_NATIVE_RESULTS_20261015 WHERE FAILED=1
ORDER BY JOB_RUN_ID, BUSINESS_RULE_ID, LAB_ROW_ID;
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schema', required=True, help='Your unquoted Db2 schema identifier')
    parser.add_argument('--audit-csv', type=Path, help='Your downloaded native audit, after the first execution')
    parser.add_argument('--run-id', help='Select one execution if the audit contains several')
    args = parser.parse_args()
    schema = args.schema.upper()
    if not re.fullmatch(r'[A-Z_][A-Z0-9_]{0,127}', schema):
        parser.error('Use a simple unquoted Db2 schema: letters, digits and underscores.')
    if args.run_id and not args.audit_csv:
        parser.error('--run-id requires --audit-csv')
    config = discover_run(args.audit_csv,args.run_id) if args.audit_csv else None
    out = ROOT/'local/prepared'
    out.mkdir(parents=True,exist_ok=True)
    for source in (ROOT/'sql').glob('*.sql'):
        (out/source.name).write_text(source.read_text().replace('{{SCHEMA}}',schema))
    prompt = (ROOT/'rules/ai-authoring-refined-prompt.txt').read_text().replace('{{SCHEMA}}',schema)
    (out/'granite-prompt.txt').write_text(prompt)
    if config:
        config['schema']=schema
        (ROOT/'local/ibm-run.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
        (out/'07_native_business_report.sql').write_text(native_report(schema,config))
    print(json.dumps({'prepared':str(out),'schema':schema,'own_ibm_ids_discovered':config is not None},indent=2))


if __name__=='__main__':
    main()
