"""Read recorded account exemptions from the HCAD Online Tax Bills table."""
import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

from pipeline import atomic_json, fetch, plain_text

SOURCE = 'https://public.hcad.org/resources/taxbill.asp'


def parse(html, account, year):
    text = plain_text(html)
    heading = re.search(r'Exemptions and Jurisdictions\nExemption Type\nDistricts\nJurisdictions\n'
                        r'Exemption Value\nARB Status\n\d{4} Rate\n(\d{4}) Rate\nOnline Tax Bill\n', text)
    if not heading or heading[1] != str(year) or not re.search(
            r'Links to online tax bill information for account ' + re.escape(account) + r'\b', text):
        raise ValueError('HCAD account, year or exemption table could not be verified')
    entries = re.match(r'(.+?)\n\d{3}\n[^\n]+', text[heading.end():], re.S)
    if not entries:
        raise ValueError('HCAD exemption labels or jurisdiction rows missing')
    labels = entries[1].splitlines()
    home = None
    if any(re.fullmatch(r'Residential Homestead(?:\s*\(Multiple\))?', label, re.I) for label in labels):
        home = True
    elif labels == ['None']:
        home = False
    return dict(homestead=home, exemption_labels=labels)


def observe(account, year, directory):
    if not re.fullmatch(r'\d{13}', account) or not re.fullmatch(r'20\d{2}', str(year)):
        raise ValueError('Invalid HCAD account or tax year')
    url = SOURCE + '?' + urlencode(dict(acct=account, card=1, taxyear=year))
    root = Path(directory)
    raw_dir = root / 'raw'
    raw_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    result = dict(account=account, tax_year=int(year), source=url, retrieved_at=now,
                  homestead=None, status='UNKNOWN')
    try:
        html = fetch(url, attempts=2)
        raw = html.encode('utf-8')
        sha = hashlib.sha256(raw).hexdigest()
        (raw_dir / (sha + '.html')).write_bytes(raw)
        result.update(sha256=sha)
        result.update(parse(html, account, year))
        if result['homestead'] is not None:
            result['status'] = 'OBSERVED'
    except (OSError, ValueError) as exc:
        result['error'] = str(exc)
    atomic_json(root / (account + '.json'), result)
    return result


def attach(document, directory):
    """Join by normalized account and confirmed appraisal year."""
    records = []
    for row in document['records']:
        account = row['account']
        record = row
        if re.fullmatch(r'\d{13}', account):
            path = Path(directory) / (account + '.json')
            try:
                observation = json.loads(path.read_text(encoding='utf-8'))
                age = datetime.now(timezone.utc) - datetime.fromisoformat(observation['retrieved_at'])
                year = int(row['hcad_gis']['tax_year'])
                url = SOURCE + '?' + urlencode(dict(acct=account, card=1, taxyear=year))
                if (observation['account'] == account and observation['tax_year'] == year
                        and observation['source'] == url and timedelta(0) <= age <= timedelta(days=2)):
                    fields = ('account', 'tax_year', 'source', 'retrieved_at', 'homestead', 'status', 'sha256')
                    record = dict(row, hcad_exemption={key: observation.get(key) for key in fields})
            except (KeyError, TypeError, ValueError, OSError):
                pass
        records.append(record)
    return dict(document, records=records)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--year', type=int, required=True)
    args = parser.parse_args()
    document = json.loads(args.inventory.read_text(encoding='utf-8'))
    rows = [r for r in document['records'] if r['action'] == 'HOLD']
    consecutive_failures = 0
    for row in rows:
        path = args.out / (row['account'] + '.json')
        if path.exists():
            try:
                saved = json.loads(path.read_text(encoding='utf-8'))
                age = datetime.now(timezone.utc) - datetime.fromisoformat(saved['retrieved_at'])
                if (saved['status'] == 'OBSERVED' and saved['tax_year'] == args.year
                        and timedelta(0) <= age <= timedelta(days=2)):
                    continue
            except (KeyError, TypeError, ValueError):
                pass
        result = observe(row['account'], args.year, args.out)
        consecutive_failures = consecutive_failures + 1 if result.get('error') else 0
        if consecutive_failures >= 3:
            break
        time.sleep(.2)


if __name__ == '__main__':
    main()
