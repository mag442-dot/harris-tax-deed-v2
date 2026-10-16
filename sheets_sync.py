"""Publish to the dedicated machine tab using the runtime service identity.

The target spreadsheet must already grant that identity edit access. This module
does not grant access, change sharing, or write Master/historical research tabs.
"""
import argparse
import json
import secrets
from pathlib import Path
from urllib.parse import quote
from reporting import HEADERS, publication_requests

BASE = 'https://sheets.googleapis.com/v4/spreadsheets/'
TAB = 'V2 Inventory'


def historical_warnings(legacy, delta):
    warnings = {}
    for row in legacy[1:]:
        if len(row) <= 7 or not row[7]:
            continue
        parts = []
        for index, prefix in ((17, ''), (5, 'Historical status: '), (21, 'Historical disposition: ')):
            value = str(row[index] or '') if len(row) > index else ''
            if index == 17 and value and value != 'UNKNOWN':
                parts.append(value)
            elif index != 17 and any(x in value.upper() for x in ('HOLD', 'NO BID', 'CANCEL')):
                parts.append(prefix + value)
        if parts:
            warnings[str(row[7])] = ' | '.join(parts)
    for row in delta[1:]:
        if len(row) <= 11 or not row[0] or not any(x in str(row[11]).upper() for x in ('HOLD', 'NO BID')):
            continue
        account = str(row[0])
        warnings[account] = ' | '.join(str(x) for x in (warnings.get(account), row[7], row[11]) if x)
    return warnings


def publish(document, spreadsheet_id, session):
    url = BASE + spreadsheet_id
    def get(path, params=None):
        response = session.get(path, params=params, timeout=45)
        response.raise_for_status()
        return response.json()
    meta = get(url, {'fields': 'spreadsheetUrl,sheets(properties(sheetId,title,gridProperties))'})
    sheets = {s['properties']['title']: s['properties'] for s in meta['sheets']}
    def values(title, area):
        escaped = "'" + title.replace("'", "''") + "'!" + area
        return get(url + '/values/' + quote(escaped, safe=''),
                   {'valueRenderOption': 'UNFORMATTED_VALUE'}).get('values', [])
    legacy = values('Legacy 93 - UNVERIFIED', 'A1:X150') if 'Legacy 93 - UNVERIFIED' in sheets else []
    delta = values('Nov03 Delta Verified', 'A1:L100') if 'Nov03 Delta Verified' in sheets else []
    existing = sheets.get(TAB)
    if existing:
        header = values(TAB, 'A1:AA1')
        if not header or header[0] != HEADERS:
            raise ValueError('Staging header differs from expected machine schema; refusing overwrite')
        sheet_id = existing['sheetId']
    else:
        used = {p['sheetId'] for p in sheets.values()}
        sheet_id = secrets.randbelow(2_000_000_000) + 1
        while sheet_id in used:
            sheet_id = secrets.randbelow(2_000_000_000) + 1
    requests = publication_requests(document, sheet_id, TAB, historical_warnings(legacy, delta),
                                    create=existing is None)
    height = len(document['records']) + 1
    if existing:
        grid = existing['gridProperties']
        requests.insert(0, {'updateSheetProperties': {'properties': {'sheetId': sheet_id,
            'gridProperties': {'rowCount': max(height, grid['rowCount']),
                               'columnCount': max(len(HEADERS), grid['columnCount'])}},
                               'fields': 'gridProperties(rowCount,columnCount)'}})
        if grid['rowCount'] > height:
            requests.append({'repeatCell': {'range': {'sheetId': sheet_id, 'startRowIndex': height,
                  'endRowIndex': grid['rowCount'], 'startColumnIndex': 0, 'endColumnIndex': len(HEADERS)},
                  'cell': {}, 'fields': 'userEnteredValue'}})
    response = session.post(url + ':batchUpdate', json={'requests': requests}, timeout=90)
    response.raise_for_status()
    accounts = values(TAB, 'A2:A' + str(height))
    expected = [r['account'] for r in document['records']]
    if [r[0] for r in accounts] != expected:
        raise RuntimeError('Sheets account readback mismatch after publication')
    return dict(spreadsheet_url=meta['spreadsheetUrl'], tab=TAB, sheet_id=sheet_id,
                records=len(expected), status='VERIFIED_READBACK')


def main():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--spreadsheet-id', required=True)
    args = parser.parse_args()
    credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/spreadsheets'])
    print(json.dumps(publish(json.loads(args.inventory.read_text()), args.spreadsheet_id,
                             AuthorizedSession(credentials)), indent=2))


if __name__ == '__main__':
    main()
