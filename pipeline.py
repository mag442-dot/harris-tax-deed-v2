"""Auditable listing ingestion. Python 3.12+, standard library only."""
import argparse
import csv
import hashlib
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

SOURCE = 'https://www.hctax.net/Property/Listings/TaxSaleListing.cshtml'


class QualityError(ValueError):
    pass


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if not self.hidden and tag in ('div', 'p', 'br', 'tr', 'td', 'th', 'h2', 'h3', 'h4', 'li'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
        if not self.hidden and tag in ('div', 'p', 'br', 'tr', 'td', 'th', 'h2', 'h3', 'h4', 'li', 'button'):
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(html):
    parser = PageText()
    parser.feed(html)
    return '\n'.join(' '.join(line.split()) for line in ''.join(parser.parts).splitlines() if line.strip())


def money(block, label):
    found = re.search(re.escape(label) + r'\s*:\s*\$\s*([\d,]+(?:\.\d{2})?)', block, re.I)
    return str(Decimal(found[1].replace(',', '')).quantize(Decimal('.01'))) if found else None


def parse_listing(html, expected_date, min_records=50):
    text = plain_text(html)
    match = re.search(r'Sale Date\s*:\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})', text)
    if not match:
        raise QualityError('Sale date missing; refusing publication')
    sale_date = datetime.strptime(match[1], '%B %d, %Y').date().isoformat()
    if sale_date != expected_date:
        raise QualityError(f'Sale date {sale_date} differs from requested {expected_date}')
    starts = list(re.finditer(r'Account\s*#\s*:\s*(\d{13})\b', text, re.I))
    records = []
    for index, start in enumerate(starts):
        block = text[start.start():starts[index + 1].start() if index + 1 < len(starts) else len(text)]
        block = re.split(r'\nClose\b', block, maxsplit=1)[0]
        def field(pattern):
            m = re.search(pattern, block, re.I)
            return m[1].strip() if m else None
        account = start[1]
        cause = field(r'Cause\s*#\s*:\s*([^\s]+)')
        precinct = field(r'Precinct\s*:\s*(?:Precinct\s*)?([1-8])\b')
        sale_type = field(r'(?:^|\n)Type\s*:\s*([^\n]+)')
        sale_number = field(r'Sale\s*#\s*:\s*(\d+)')
        # Detail address follows the account header. Never infer location from account.
        address_area = block.split('×', 1)[0]
        address_match = re.search(r'(?:^|\n)([^\n]*\bTX\.?\s+\d{5}(?:-\d{4})?)\s*(?:\n|$)', address_area)
        address = address_match[1].strip() if address_match else None
        raw_match = re.search(r'\n([^\n]+)\n×', block)
        address_raw = raw_match[1].strip() if raw_match and not re.search(r'Bid:|Value:|Account#|Cause#', raw_match[1]) else None
        description_match = re.search(r'(?:^|\n)Description[^\S\n]*(?:\n|$)([\s\S]*)', block, re.I)
        description = description_match[1].strip() if description_match else None
        grouped = bool(re.search(r'Sold with Account\s*#', block, re.I))
        group_target = field(r'Sold with Account\s*#\s*:?\s*(\d{13})\b')
        flags = []
        if grouped:
            flags.append('GROUP_REVIEW')
        if re.search(r'undivided|fractional|\bpercent interest\b|\b\d+/\d+\b.*interest', description or '', re.I):
            flags.append('FRACTIONAL_INTEREST')
        if (sale_type or '').upper() not in ('SALE', 'RESALE'):
            flags.append('SPECIAL_PROCEEDING')
        bid = money(block, 'Minimum Bid')
        if bid is None and not grouped:
            flags.append('MISSING_BID')
        if not address or not description:
            flags.append('MISSING_PROPERTY_DETAIL')
        records.append(dict(account=account, sale_date=sale_date, cause=cause,
                            precinct=precinct, sale_number=sale_number, sale_type=sale_type,
                            address=address, address_raw=address_raw,
                            address_status='SOURCE_REPORTED' if address else 'INCOMPLETE_OR_MISSING',
                            legal_description=description or None,
                            legal_status='SOURCE_REPORTED' if description else 'MISSING',
                            minimum_bid=bid, adjudged_value=money(block, 'Adjudged Value'),
                            grouped=grouped, group_target=group_target,
                            lot_identity_status='UNVERIFIED', flags=flags,
                            action='HOLD' if flags else 'RESEARCH',
                            homestead_status='UNKNOWN', flood_status='UNKNOWN'))
    accounts = [r['account'] for r in records]
    if len(records) < min_records:
        raise QualityError(f'Only {len(records)} records; minimum {min_records}')
    if len(set(accounts)) != len(accounts):
        raise QualityError('Duplicate accounts; refusing publication')
    if any(not r['cause'] or not r['precinct'] or not r['sale_type'] or not r['sale_number'] for r in records):
        raise QualityError('Required auction identifiers missing')
    if sum(not r['legal_description'] for r in records) > max(1, len(records) * .5):
        raise QualityError('More than half of legal descriptions missing; layout requires review')
    if sum(not r['address'] for r in records) > max(1, len(records) * .5):
        raise QualityError('More than half of source addresses missing; layout requires review')
    return records


def changes(previous, current):
    old = {r['account']: r for r in previous}
    new = {r['account']: r for r in current}
    result = []
    for account, row in new.items():
        if account not in old:
            result.append(dict(account=account, kind='NEW'))
        else:
            changed_fields = [k for k in row if row[k] != old[account].get(k)]
            if changed_fields:
                result.append(dict(account=account, kind='CHANGED', fields=changed_fields))
    for account in old.keys() - new.keys():
        result.append(dict(account=account, kind='MISSING_NEEDS_REVIEW'))
    return sorted(result, key=lambda r: r['account'])


def fetch(url, attempts=3):
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'HarrisAuctionResearch/0.1'})
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read().decode('utf-8-sig')
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == attempts - 1:
                raise
        time.sleep(2 ** attempt)


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def run(html, state_dir, sale_date, min_records=50, source=SOURCE):
    root = Path(state_dir)
    root.mkdir(parents=True, exist_ok=True)
    # Exclusive local lock prevents concurrent pointer replacement.
    import fcntl
    with (root / 'run.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        digest = hashlib.sha256(html.encode()).hexdigest()
        snapshot = root / 'snapshots' / (digest + '.html')
        snapshot.parent.mkdir(exist_ok=True)
        if not snapshot.exists():
            snapshot.write_text(html)
        now = datetime.now(timezone.utc).isoformat()
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        audit = dict(run_id=run_id, retrieved_at=now, source=source, sha256=digest, sale_date=sale_date)
        try:
            rows = parse_listing(html, sale_date, min_records)
            latest = root / sale_date / 'latest.json'
            previous = json.loads(latest.read_text())['records'] if latest.exists() else []
            if previous and len(rows) < len(previous) * .75:
                raise QualityError('Inventory fell by more than 25%; needs review')
            delta = changes(previous, rows)
            audit.update(status='PASSED', records=len(rows), changes=len(delta),
                         missing_address=sum(not r['address'] for r in rows),
                         missing_legal=sum(not r['legal_description'] for r in rows))
            document = dict(audit=audit, records=rows, changes=delta)
            atomic_json(root / 'runs' / (run_id + '.json'), document)
            atomic_json(latest, document)
            return document
        except Exception as exc:
            audit.update(status='FAILED', error=str(exc))
            atomic_json(root / 'runs' / (run_id + '.json'), dict(audit=audit))
            raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sale-date', required=True)
    parser.add_argument('--html', type=Path)
    parser.add_argument('--state-dir', default='state')
    parser.add_argument('--min-records', type=int, default=50)
    args = parser.parse_args()
    html = args.html.read_text(encoding='utf-8-sig') if args.html else fetch(SOURCE)
    result = run(html, args.state_dir, args.sale_date, args.min_records,
                 str(args.html) if args.html else SOURCE)
    print(json.dumps(result['audit'], indent=2))


if __name__ == '__main__':
    main()
