"""Machine-owned staging report. No edits to historical or underwriting tabs."""
import re

HEADERS = ['Account', 'Sale Date', 'Sale Status', 'Research Action', 'Listing Address',
           'HCAD Address', 'Lot SF', 'Minimum Bid', 'HCAD Market Value', 'Building Value',
           'HCAD Tax Year', 'Sale Type', 'Precinct', 'Cause', 'Grouped', 'Group Target',
           'Flags', 'Homestead', 'FEMA Observation', 'Listing Legal', 'HCAD Legal', 'Historical Warning',
           'Listing Source', 'HCAD Source', 'GIS Retrieved UTC', 'State Class', 'FEMA Source']


def report_rows(document, warnings=None):
    warnings = warnings or {}
    matrix = [HEADERS]
    for row in document['records']:
        g = row.get('hcad_gis', {})
        fema = row.get('fema', {})
        flags = list(row.get('flags', []))
        warning = warnings.get(row['account'], '')
        address = ' '.join((str(row.get('address') or ''), str(g.get('address') or '')))
        action = row['action']
        flood_text = row.get('flood_status', 'UNKNOWN')
        if fema:
            flood_text = fema['status']
            if fema['status'] == 'INTERSECTION_OBSERVED':
                flood_text = '/'.join(fema.get('zones', []))
                flood_text += ' | ' + '; '.join(fema.get('subtypes', []))
                flood_text += ' | coverage not measured'
            if fema.get('sfha_intersects'):
                flags.append('FEMA_SFHA_INTERSECTION')
                if action != 'NO_BID':
                    action = 'HOLD'
            if fema.get('floodway_intersects'):
                flags.append('FEMA_FLOODWAY_INTERSECTION')
                if action != 'NO_BID':
                    action = 'HOLD'
        if re.search(r'\bBAYTOWN\b', address, re.I):
            flags.append('EXCLUDED_BAYTOWN')
            action = 'NO_BID'
        if 'FRACTIONAL_INTEREST' in flags or re.search(r'fractional|undivided|REJECT', warning, re.I):
            action = 'NO_BID'
        if warning:
            flags.append('HISTORICAL_REVIEW')
            if action != 'NO_BID':
                action = 'HOLD'
        matrix.append([row['account'], row['sale_date'], row.get('sale_status', 'UNKNOWN'), action,
                       row.get('address') or row.get('address_raw'), g.get('address'), g.get('lot_sf'),
                       float(row['minimum_bid']) if row.get('minimum_bid') is not None else None,
                       g.get('market_value'), g.get('building_value'), g.get('tax_year'), row.get('sale_type'),
                       row.get('precinct'), row.get('cause'), row.get('grouped'), row.get('group_target'),
                       '; '.join(dict.fromkeys(flags)), row.get('homestead_status', 'UNKNOWN'),
                       flood_text, row.get('legal_description'),
                       g.get('legal_description'), warning, document['audit']['source'],
                       g.get('source'), g.get('retrieved_at'), g.get('state_class'), fema.get('source')])
    return matrix


def cell(value):
    if value is None:
        return {}
    if isinstance(value, bool):
        return {'userEnteredValue': {'boolValue': value}}
    if isinstance(value, (int, float)):
        return {'userEnteredValue': {'numberValue': value}}
    # Explicit stringValue prevents formula injection and preserves leading zeros.
    return {'userEnteredValue': {'stringValue': str(value)}}


def publication_requests(document, sheet_id, title, warnings=None, create=True):
    matrix = report_rows(document, warnings)
    height, width = len(matrix), len(HEADERS)
    area = dict(sheetId=sheet_id, startRowIndex=0, endRowIndex=height,
                startColumnIndex=0, endColumnIndex=width)
    requests = []
    if create:
        requests.append({'addSheet': {'properties': {'sheetId': sheet_id, 'title': title,
                        'gridProperties': {'rowCount': max(300, height), 'columnCount': width,
                                           'frozenRowCount': 1, 'frozenColumnCount': 1}}}})
    requests += [
        {'updateCells': {'range': area, 'rows': [{'values': [cell(v) for v in row]} for row in matrix],
                         'fields': 'userEnteredValue'}},
        {'repeatCell': {'range': area, 'cell': {'userEnteredFormat': {
            'textFormat': {'fontFamily': 'Arial', 'fontSize': 10},
            'verticalAlignment': 'TOP', 'wrapStrategy': 'CLIP'}}, 'fields': 'userEnteredFormat'}},
        {'repeatCell': {'range': dict(area, endRowIndex=1), 'cell': {'userEnteredFormat': {
            'backgroundColor': {'red': .92, 'green': .92, 'blue': .92},
            'textFormat': {'bold': True}, 'wrapStrategy': 'WRAP'}},
            'fields': 'userEnteredFormat(backgroundColor,textFormat.bold,wrapStrategy)'}},
        {'setBasicFilter': {'filter': {'range': area}}},
        {'updateDimensionProperties': {'range': {'sheetId': sheet_id, 'dimension': 'COLUMNS',
             'startIndex': 0, 'endIndex': width}, 'properties': {'pixelSize': 145}, 'fields': 'pixelSize'}},
        {'updateDimensionProperties': {'range': {'sheetId': sheet_id, 'dimension': 'COLUMNS',
             'startIndex': 4, 'endIndex': 6}, 'properties': {'pixelSize': 320}, 'fields': 'pixelSize'}},
        {'updateDimensionProperties': {'range': {'sheetId': sheet_id, 'dimension': 'COLUMNS',
             'startIndex': 19, 'endIndex': 25}, 'properties': {'pixelSize': 320}, 'fields': 'pixelSize'}},
        {'updateDimensionProperties': {'range': {'sheetId': sheet_id, 'dimension': 'COLUMNS',
             'startIndex': 18, 'endIndex': 19}, 'properties': {'pixelSize': 420}, 'fields': 'pixelSize'}},
        {'repeatCell': {'range': dict(area, startRowIndex=1, startColumnIndex=7, endColumnIndex=10),
             'cell': {'userEnteredFormat': {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}}},
             'fields': 'userEnteredFormat.numberFormat'}},
        {'repeatCell': {'range': dict(area, startRowIndex=1, startColumnIndex=6, endColumnIndex=7),
             'cell': {'userEnteredFormat': {'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0'}}},
             'fields': 'userEnteredFormat.numberFormat'}}]
    return requests
