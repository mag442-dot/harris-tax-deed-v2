"""FEMA parcel intersection observations; absence of a match never means safe."""
import argparse
import json
import urllib.request
import urllib.error
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode
from pipeline import atomic_json

LAYER = 'https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28'


def query(geometry):
    rings = geometry.get('rings', [])
    if not rings or any(len(r) < 4 for r in rings):
        raise ValueError('Missing or invalid parcel rings')
    if any(not (-180 <= p[0] <= 180 and -90 <= p[1] <= 90) for r in rings for p in r):
        raise ValueError('Parcel geometry must be longitude/latitude (EPSG:4326)')
    payload = urlencode(dict(f='json', where='1=1', geometry=json.dumps(geometry),
                            geometryType='esriGeometryPolygon', inSR='4326',
                            spatialRel='esriSpatialRelIntersects', returnGeometry='false',
                            outFields='FLD_ZONE,ZONE_SUBTY,SFHA_TF,DFIRM_ID,FLD_AR_ID')).encode()
    request = urllib.request.Request(LAYER + '/query', data=payload,
                                     headers={'User-Agent': 'HarrisAuctionResearch/0.1'})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.load(response)
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 1:
                raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 1:
                raise
        time.sleep(2)
    if data.get('error') or data.get('exceededTransferLimit'):
        raise ValueError('FEMA error or truncated response: ' + str(data.get('error', 'limit')))
    if 'features' not in data:
        raise ValueError('FEMA response missing features')
    return data


def summarize(data):
    attributes = [f['attributes'] for f in data['features']]
    if not attributes:
        return dict(status='NO_MATCH_REQUIRES_REVIEW', zones=[], sfha_intersects=None,
                    floodway_intersects=None, coverage_status='UNKNOWN')
    return dict(status='INTERSECTION_OBSERVED',
                zones=sorted({a.get('FLD_ZONE') for a in attributes if a.get('FLD_ZONE')}),
                subtypes=sorted({a.get('ZONE_SUBTY') for a in attributes if a.get('ZONE_SUBTY')}),
                sfha_intersects=True if any(a.get('SFHA_TF') == 'T' for a in attributes) else None,
                floodway_intersects=True if any('FLOODWAY' in (a.get('ZONE_SUBTY') or '').upper()
                                                for a in attributes) else None,
                coverage_status='NOT_MEASURED',
                note='Intersections only; no parcel-area percentages or full-coverage conclusion.')


def enrich_flood(document, directory, limit=None, previous=None):
    root = Path(directory)
    output = []
    consecutive_failures = 0
    queried = 0
    prior = {r['account']: r for r in (previous or {}).get('records', [])}
    for row in document['records']:
        geometry = row.get('hcad_gis', {}).get('geometry')
        observation = dict(source=LAYER, retrieved_at=datetime.now(timezone.utc).isoformat())
        old = prior.get(row['account'], {})
        cached = old.get('fema', {})
        recent = False
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(cached['retrieved_at'])
            recent = timedelta(0) <= age <= timedelta(days=7)
        except (KeyError, ValueError, TypeError):
            pass
        if not geometry:
            observation.update(status='NO_PARCEL_GEOMETRY')
        elif (cached.get('status') == 'INTERSECTION_OBSERVED' and recent
              and old.get('hcad_gis', {}).get('geometry') == geometry):
            observation = dict(cached, cache_reused=True)
        elif limit is not None and queried >= limit:
            observation.update(status='NOT_QUERIED_LIMIT')
        elif consecutive_failures >= 3:
            observation.update(status='BLOCKED_CIRCUIT_OPEN')
        else:
            queried += 1
            time.sleep(.3)
            try:
                raw = query(geometry)
                atomic_json(root / 'raw' / (row['account'] + '.json'), dict(observation, response=raw))
                observation.update(summarize(raw))
                consecutive_failures = 0
            except Exception as exc:
                consecutive_failures += 1
                observation.update(status='BLOCKED', error=str(exc))
        output.append(dict(row, fema=observation))
    result = dict(document, records=output)
    atomic_json(root / 'enriched.json', result)
    counts = {s: sum(r['fema']['status'] == s for r in output)
              for s in sorted({r['fema']['status'] for r in output})}
    atomic_json(root / 'summary.json', counts)
    return counts


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--inventory', type=Path, required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--limit', type=int)
    p.add_argument('--resume', type=Path)
    args = p.parse_args()
    previous = json.loads(args.resume.read_text()) if args.resume and args.resume.exists() else None
    print(json.dumps(enrich_flood(json.loads(args.inventory.read_text()), args.out, args.limit, previous), indent=2))
