"""Batch official parcel GIS enrichment; never equates missing data with safety."""
import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from pipeline import atomic_json, fetch

LAYER = 'https://www.gis.hctx.net/arcgis/rest/services/HCAD/Parcels/MapServer/0'
FIELDS = 'acct_num,HCAD_NUM,tax_year,site_str_num,site_str_pfx,site_str_num_sfx,site_str_name,site_str_sfx,site_str_sfx_dir,site_city,site_zip,land_sqft,bld_value,impr_value,total_market_val,total_appraised_val,state_class,land_use,legal_dscr_1,legal_dscr_2,legal_dscr_3,legal_dscr_4,clerk_id,activeAccount_flag'


def query(accounts):
    if not accounts or any(not re.fullmatch(r'\d{13}', a) for a in accounts):
        raise ValueError('Expected 13-digit account strings')
    where = 'acct_num IN (' + ','.join("'" + a + "'" for a in accounts) + ')'
    url = LAYER + '/query?' + urlencode(dict(where=where, outFields=FIELDS,
                                             returnGeometry='true', outSR='4326', f='json'))
    data = json.loads(fetch(url))
    if 'error' in data or data.get('exceededTransferLimit'):
        raise ValueError('GIS query error or truncated result: ' + str(data.get('error', 'limit')))
    return url, data


def summarize(features):
    if len(features) != 1:
        return dict(status='NOT_FOUND' if not features else 'MULTIPLE_MATCHES',
                    feature_count=len(features), homestead_status='UNKNOWN')
    a = features[0]['attributes']
    street = ' '.join(str(a[k]) for k in ('site_str_num', 'site_str_num_sfx', 'site_str_pfx',
                       'site_str_name', 'site_str_sfx', 'site_str_sfx_dir') if a.get(k) is not None and str(a[k]).strip())
    return dict(status='SOURCE_REPORTED', tax_year=a.get('tax_year'),
                address=', '.join(x for x in (street, a.get('site_city'), a.get('site_zip')) if x),
                lot_sf=a.get('land_sqft'), market_value=a.get('total_market_val'),
                appraised_value=a.get('total_appraised_val'), building_value=a.get('bld_value'),
                state_class=a.get('state_class'), land_use=a.get('land_use'),
                legal_description=' '.join(a.get('legal_dscr_' + str(i)) or '' for i in range(1, 5)).strip(),
                clerk_id=a.get('clerk_id'), homestead_status='UNKNOWN',
                geometry=features[0].get('geometry'))


def enrich(document, directory):
    root = Path(directory)
    rows = document['records']
    results = {}
    for offset in range(0, len(rows), 25):
        batch = [r['account'] for r in rows[offset:offset + 25]]
        now = datetime.now(timezone.utc).isoformat()
        try:
            url, raw = query(batch)
            atomic_json(root / 'gis_raw' / (str(offset) + '.json'), dict(source=url, retrieved_at=now, response=raw))
            grouped = defaultdict(list)
            for feature in raw.get('features', []):
                grouped[str(feature['attributes'].get('acct_num'))].append(feature)
            for account in batch:
                results[account] = dict(summarize(grouped[account]), source=url, retrieved_at=now)
        except Exception as exc:
            for account in batch:
                results[account] = dict(status='BLOCKED', error=str(exc), source=LAYER,
                                        retrieved_at=now, homestead_status='UNKNOWN')
    enriched = dict(document, records=[dict(r, hcad_gis=results[r['account']]) for r in rows])
    atomic_json(root / 'enriched.json', enriched)
    counts = {status: sum(r['status'] == status for r in results.values())
              for status in sorted(set(r['status'] for r in results.values()))}
    atomic_json(root / 'enrichment_summary.json', counts)
    return counts


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--inventory', type=Path, required=True)
    p.add_argument('--out', required=True)
    args = p.parse_args()
    print(json.dumps(enrich(json.loads(args.inventory.read_text()), args.out), indent=2))
