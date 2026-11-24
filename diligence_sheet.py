"""Publish December decisions to a sale-specific machine-owned tab."""
import secrets
from urllib.parse import quote

from diligence import SALE_DATE, SPREADSHEET_ID
from reporting import cell
from sheets_sync import BASE

TAB = 'V2 Diligence Dec01 2026'
HEADERS = [
    'Account', 'Sale Date', 'Address', 'ZIP', 'Lot SF', 'Sale Status', 'Disposition',
    'Rank', 'Minimum Bid', 'Maximum Bid', 'Base ROI', 'Review Issues', 'Exclusions',
    *(f'A{i}' for i in range(1, 11)), 'Official source', 'Source SHA-256',
]


def rows(document):
    inventory = document['diligence']['inventory']
    if document['audit']['sale_date'] != SALE_DATE or not inventory['official']:
        raise ValueError('Verified December source required for publication')
    matrix = [HEADERS]
    for row in document['records']:
        modules = row['modules']
        parcel = modules['A2']['data'] or {}
        audit = modules['A9']
        decision = modules['A10']
        scenarios = modules['A8']['data']
        matrix.append([
            row['account'], SALE_DATE, row.get('address') or row.get('address_raw'),
            parcel.get('zip'), parcel.get('lot_sf'), row['sale_status'], decision['status'],
            decision['rank'], float(row['minimum_bid']) if row.get('minimum_bid') is not None else None,
            float(decision['maximum_bid']) if decision['maximum_bid'] is not None else None,
            float(scenarios['base']['roi']) if scenarios else None, ', '.join(audit['issues']),
            ', '.join(audit['exclusions']), *(modules[f'A{i}']['status'] for i in range(1, 11)),
            document['audit']['source'], document['audit']['sha256'],
        ])
    return matrix


def requests_for(matrix, sheet_id, existing=None):
    width, height = len(HEADERS), len(matrix)
    prior_height = existing['rowCount'] if existing else 0
    grid = dict(rowCount=max(300, height, prior_height),
                columnCount=max(width, existing['columnCount'] if existing else 0))
    rectangle = dict(sheetId=sheet_id, startRowIndex=0, endRowIndex=max(height, prior_height),
                     startColumnIndex=0, endColumnIndex=width)
    if existing:
        requests = [{'updateSheetProperties': {
            'properties': dict(sheetId=sheet_id, gridProperties=grid),
            'fields': 'gridProperties(rowCount,columnCount)',
        }}]
    else:
        requests = [{'addSheet': {'properties': dict(
            sheetId=sheet_id, title=TAB, gridProperties=dict(grid, frozenRowCount=1))}}]
    requests += [
        {'updateCells': {'range': rectangle,
                         'rows': [{'values': [cell(value) for value in row]} for row in matrix],
                         'fields': 'userEnteredValue'}},
        {'setBasicFilter': {'filter': {'range': dict(rectangle, endRowIndex=height)}}},
        {'repeatCell': {'range': dict(rectangle, endRowIndex=1),
                        'cell': {'userEnteredFormat': {'textFormat': {'bold': True},
                                                       'wrapStrategy': 'WRAP'}},
                        'fields': 'userEnteredFormat(textFormat.bold,wrapStrategy)'}},
        {'repeatCell': {'range': dict(rectangle, startRowIndex=1, endRowIndex=height,
                                      startColumnIndex=10, endColumnIndex=11),
                        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'PERCENT',
                                                                        'pattern': '0.00%'}}},
                        'fields': 'userEnteredFormat.numberFormat'}},
    ]
    return requests


def publish(document, session, spreadsheet_id=SPREADSHEET_ID):
    if spreadsheet_id != SPREADSHEET_ID:
        raise ValueError('December publication destination mismatch')
    matrix = rows(document)
    url = BASE + spreadsheet_id

    def get(path, params=None):
        response = session.get(path, params=params, timeout=45)
        response.raise_for_status()
        return response.json()

    def values(area):
        return get(url + '/values/' + quote(f"'{TAB}'!{area}", safe=''),
                   {'valueRenderOption': 'UNFORMATTED_VALUE'}).get('values', [])

    meta = get(url, {'fields': 'spreadsheetUrl,sheets(properties(sheetId,title,gridProperties))'})
    sheets = {item['properties']['title']: item['properties'] for item in meta['sheets']}
    existing = sheets.get(TAB)
    if existing:
        if values('A1:Y1') != [HEADERS]:
            raise ValueError('December tab header differs from expected machine schema')
        sheet_id = existing['sheetId']
    else:
        ids = {item['sheetId'] for item in sheets.values()}
        sheet_id = secrets.randbelow(2_000_000_000) + 1
        while sheet_id in ids:
            sheet_id = secrets.randbelow(2_000_000_000) + 1
    requests = requests_for(matrix, sheet_id, existing and existing['gridProperties'])
    response = session.post(url + ':batchUpdate', json={'requests': requests}, timeout=90)
    response.raise_for_status()
    readback = values(f'A1:Y{len(matrix)}')
    if readback != [[value if value is not None else '' for value in row] for row in matrix]:
        raise RuntimeError('December publication readback differs from source')
    return dict(spreadsheet_url=meta['spreadsheetUrl'], sheet_id=sheet_id, tab=TAB,
                records=len(matrix) - 1, status='VERIFIED_READBACK')
