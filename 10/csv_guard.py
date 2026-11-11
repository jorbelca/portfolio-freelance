"""Validate synthetic order exports. Standard library only."""
import argparse
import csv
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path

REQUIRED = ('order_id', 'date', 'quantity', 'unit_price', 'total')


def inspect(path):
    issues = []
    rows = 0
    seen = set()

    def flag(line, field, message):
        issues.append({'line': line, 'field': field, 'message': message})

    with Path(path).open(encoding='utf-8-sig', newline='') as source:
        reader = csv.reader(source, strict=True)
        headers = next(reader, [])
        missing = sorted(set(REQUIRED) - set(headers))
        duplicates = sorted(k for k, count in Counter(headers).items() if count > 1)
        if missing or duplicates:
            if missing:
                flag(1, 'schema', 'Missing columns: ' + ', '.join(missing))
            if duplicates:
                flag(1, 'schema', 'Duplicate columns: ' + ', '.join(duplicates))
            return {'rows': 0, 'issues': issues}
        if not headers:
            flag(1, 'schema', 'Empty file')
        for values in reader:
            rows += 1
            line = reader.line_num
            if len(values) != len(headers):
                flag(line, 'schema', 'Row width does not match header')
                continue
            row = dict(zip(headers, (value.strip() for value in values)))
            identifier = row['order_id']
            if not identifier:
                flag(line, 'order_id', 'Required value')
            elif identifier in seen:
                flag(line, 'order_id', 'Duplicate order ID')
            seen.add(identifier)
            try:
                parsed = date.fromisoformat(row['date'])
                if parsed.isoformat() != row['date']:
                    raise ValueError
            except ValueError:
                flag(line, 'date', 'Expected a valid YYYY-MM-DD date')
            numbers = {}
            for field in ('quantity', 'unit_price', 'total'):
                try:
                    value = Decimal(row[field])
                    if not value.is_finite() or value < 0:
                        raise ValueError
                    if field == 'quantity':
                        if value == 0 or value != value.to_integral_value() or value > 1000000:
                            raise ValueError
                    elif value > Decimal('1000000000') or value != value.quantize(Decimal('.01')):
                        raise ValueError
                    numbers[field] = value
                except (InvalidOperation, ValueError):
                    flag(line, field, 'Expected positive integer ≤ 1000000' if field == 'quantity'
                         else 'Expected non-negative amount ≤ 1000000000 with at most 2 decimal places')
            if len(numbers) == 3 and numbers['quantity'] * numbers['unit_price'] != numbers['total']:
                flag(line, 'total', 'Total differs from quantity × unit price')
    return {'rows': rows, 'issues': issues}


def report(result):
    issues = result['issues']
    counts = Counter(issue['field'] for issue in issues)
    bars = ''.join(f'<div class="bar"><span>{escape(field)}</span><meter min="0" max="{max(counts.values())}" value="{count}"></meter><b>{count}</b></div>' for field, count in counts.items())
    table = ''.join(f'<tr><td>{i["line"]}</td><td><code>{escape(i["field"])}</code></td><td>{escape(i["message"])}</td></tr>' for i in issues)
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>CSV Guard · Quality report</title>
<style>:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#101718;color:#e5eeeb;font:16px/1.6 system-ui,sans-serif}main{max-width:1050px;margin:auto;padding:48px 24px}header{border-bottom:1px solid #33423e;padding-bottom:28px}.eyebrow{color:#89d6b5;font-size:12px;letter-spacing:3px}h1{font-size:clamp(36px,7vw,64px);line-height:1.1;margin:20px 0}p{color:#a6b9b2}.cards{display:flex;gap:16px;margin:30px 0;flex-wrap:wrap}.card{flex:1;min-width:160px;background:#1a2522;padding:24px;border:1px solid #33423e;border-radius:12px}.card strong{display:block;font-size:36px;color:#aff0ce}.bar{display:flex;align-items:center;gap:16px;margin:12px 0}.bar span{width:110px}meter{flex:1;height:16px}table{width:100%;border-collapse:collapse;text-align:left}td,th{padding:16px;border-bottom:1px solid #33423e}th{color:#89d6b5;font-size:12px;text-transform:uppercase}code{color:#f3c985}.scroll{overflow-x:auto}footer{margin-top:36px;color:#a6b9b2;font-size:13px}</style><main><header><div class="eyebrow">CSV GUARD / LOCAL DATA QUALITY</div><h1>Find the error.<br>Trace it to the row.</h1><p>Deterministic checks for order exports. No API calls. No file uploads.</p></header>''' + f'''
<section class="cards" aria-label="Summary"><div class="card">Rows inspected<strong>{result['rows']}</strong></div><div class="card">Issues found<strong>{len(issues)}</strong></div><div class="card">Result<strong>{'Review' if issues else 'Pass'}</strong></div></section>
<h2>Issues by field</h2>{bars or '<p>No issues detected by the implemented checks.</p>'}<h2>Actionable findings</h2><div class="scroll"><table><thead><tr><th>CSV line*</th><th>Field</th><th>Reason</th></tr></thead><tbody>{table or '<tr><td colspan="3">All implemented checks passed.</td></tr>'}</tbody></table></div><footer>*Physical line where the record ends, including the header. One row can have multiple issues. Checks cover schema, IDs, dates, quantities and totals; they do not verify business truth. Input is never modified.</footer></main></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.report.resolve():
        parser.error('Report path must differ from input')
    try:
        result = inspect(args.input)
        with args.report.open('x', encoding='utf-8') as output:
            output.write(report(result))
    except (OSError, UnicodeError, csv.Error) as error:
        parser.exit(2, f'Error: {error}\n')
    print(f"{result['rows']} rows · {len(result['issues'])} issues · {args.report}")
    return 1 if result['issues'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
