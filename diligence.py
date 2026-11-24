"""December due diligence over the existing official inventory and GIS observations."""
import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from pathlib import Path
from statistics import median
from urllib.parse import urlsplit

from pipeline import SOURCE, atomic_json

SALE_DATE = '2026-12-01'
SPREADSHEET_ID = '1UgtW_0Qeg8aYa0hlRbfGVrR5_-Jlf4Lvz8YhMmw1iOg'
REFERENCE_COUNT = 157
ZIP_PRIORITY = ('77028', '77021', '77078', '77033', '77051', '77016', '77088')
VERSION = 4
UNKNOWN = 'UNKNOWN'


def amount(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        return None
    return result if result.is_finite() and result >= 0 else None


def digest(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def status(known, data=None, evidence=None):
    return dict(status='OBSERVED' if known else UNKNOWN, data=data, evidence=evidence)


def evidence_for(bundle, name, account):
    """Consume normalized, account-specific observations from an authorized producer."""
    entry = bundle.get(name)
    if not isinstance(entry, dict) or entry.get('account') != account or entry.get('sale_date') != SALE_DATE:
        return None
    source = urlsplit(str(entry.get('source') or ''))
    if source.scheme != 'https' or not source.hostname or source.username or source.password:
        return None
    try:
        date.fromisoformat(entry['observed_on'])
    except (KeyError, ValueError, TypeError):
        return None
    if not isinstance(entry.get('reference'), str) or not entry['reference'].strip():
        return None
    return entry if isinstance(entry.get('data'), dict) else None


def observation(bundle, name, account, validate):
    proof = evidence_for(bundle, name, account)
    data = proof['data'] if proof else {}
    return status(bool(proof and validate(data)), data, proof)


def comparable_sales(data):
    sales = data.get('sales')
    if not isinstance(sales, list) or len(sales) < 3:
        return False
    references = set()
    for sale in sales:
        if not isinstance(sale, dict) or sale.get('property_type') != 'DUPLEX' or sale.get('closed') is not True:
            return False
        if not (amount(sale.get('price')) and amount(sale.get('building_sf'))):
            return False
        reference = sale.get('reference')
        if not isinstance(reference, str) or not reference.strip() or reference in references:
            return False
        try:
            if date.fromisoformat(sale['closed_on']) > date.fromisoformat(SALE_DATE):
                return False
        except (KeyError, ValueError, TypeError):
            return False
        references.add(reference)
    return True


def boolean_fields(data, fields):
    return all(type(data.get(field)) is bool for field in fields)


def a1(row, inventory):
    account = row['account']
    members = sorted(inventory['groups'].get(account, []))
    if row.get('grouped'):
        target = row.get('group_target')
        if target:
            members = sorted(set(members) | set(inventory['groups'].get(target, [])) | {target})
    known = (inventory['official'] and row['sale_status'] in
             {'FOR SALE', 'CANCELLED', 'CANCELED', 'WITHDRAWN', 'SOLD'} and not members
             and not row.get('grouped') and bool(row.get('legal_description'))
             and bool(row.get('address')))
    return status(known, dict(sale_status=row['sale_status'], minimum_bid=row.get('minimum_bid'),
                              cause=row.get('cause'), precinct=row.get('precinct'),
                              sale_number=row.get('sale_number'), group_target=row.get('group_target'),
                              judgment_date=row.get('judgment_date'), judgment_tax_years=row.get('judgment_tax_years'),
                              group_reference=('UNRESOLVED' if row.get('grouped') and
                                               row.get('group_target') in (None, account) else row.get('group_target')),
                              related_accounts=[x for x in members if x != account],
                              lot_identity='UNVERIFIED_GROUP' if members or row.get('grouped') else 'LISTING_ACCOUNT'),
                  inventory['audit'])


def a2(row, bundle):
    gis = row.get('hcad_gis', {})
    proof = evidence_for(bundle, 'hcad', row['account'])
    reviewed = proof['data'] if proof else {}
    exemption = row.get('hcad_exemption') or {}
    recorded_home = exemption.get('homestead')
    reviewed_home = reviewed.get('homestead')
    conflict = type(recorded_home) is bool and type(reviewed_home) is bool and recorded_home != reviewed_home
    homestead = recorded_home if type(recorded_home) is bool else reviewed_home
    vacant = reviewed.get('vacant')
    city = gis.get('city')
    zipcode = str(gis.get('zip') or '')
    if not city or not zipcode:
        match = re.search(r',\s*([^,]+),\s*(\d{5})(?:-\d{4})?$', gis.get('address') or '')
        if match:
            city, zipcode = match.groups()
    known = (gis.get('status') == 'SOURCE_REPORTED' and bool(gis.get('source')) and
             amount(gis.get('lot_sf')) is not None and bool(city) and zipcode.isdigit() and
             bool(gis.get('state_class')) and amount(gis.get('building_value')) is not None and
             type(homestead) is bool and not conflict and type(vacant) is bool and
             not (vacant and amount(gis.get('building_value'))))
    return status(known, dict(lot_sf=gis.get('lot_sf'), city=city, zip=zipcode,
                              state_class=gis.get('state_class'), building_value=gis.get('building_value'),
                              improvement_value=gis.get('improvement_value'),
                              homestead=homestead, vacant=vacant, homestead_conflict=conflict),
                  dict(gis=gis, exemption=exemption, review=proof))


def a5(row, bundle):
    fema = row.get('fema', {})
    local = observation(bundle, 'maapnext', row['account'],
                        lambda data: type(data.get('development_clear')) is bool)
    federal = observation(bundle, 'fema_review', row['account'],
                          lambda data: data.get('coverage_verified') is True and
                          boolean_fields(data, ('sfha_intersects', 'floodway_intersects')))
    reviewed = federal['data'] if federal['status'] == 'OBSERVED' else {}
    sfha = True if fema.get('sfha_intersects') is True else reviewed.get('sfha_intersects')
    floodway = True if fema.get('floodway_intersects') is True else reviewed.get('floodway_intersects')
    known = (fema.get('status') == 'INTERSECTION_OBSERVED' and bool(fema.get('source')) and
             type(sfha) is bool and type(floodway) is bool and local['status'] == 'OBSERVED')
    return status(known, dict(sfha=sfha, floodway=floodway,
                              maapnext_clear=local['data'].get('development_clear')),
                  dict(fema=fema, coverage_review=federal['evidence'], maapnext=local['evidence']))


def finance(minimum_bid, taxes, liens):
    """Simple interest on the peak financed balance for the entire holding period."""
    bid, tax, lien = map(amount, (minimum_bid, taxes, liens))
    if any(value is None for value in (bid, tax, lien)):
        return None
    equity, target = Decimal('100000'), Decimal('.20')
    scenarios = {}
    for name, sale_psf, build_psf, months in (
        ('base', 165, 105, 9), ('downside', 148.5, 115.5, 12), ('upside', 181.5, 105, 9),
    ):
        revenue = 2600 * Decimal(str(sale_psf))
        build = 2600 * Decimal(str(build_psf))
        net = revenue * Decimal('.95')
        fixed = build + Decimal('17000') + tax + lien
        interest_rate = Decimal('.12') * months / 12
        allowable = net - equity * target
        if allowable > equity:
            allowable = (allowable + equity * interest_rate) / (1 + interest_rate)
        maximum = (allowable - fixed).quantize(Decimal('.01'), rounding=ROUND_FLOOR)
        costs = fixed + bid
        interest = max(Decimal(0), costs - equity) * interest_rate
        profit = net - costs - interest
        roi = profit / equity
        if maximum >= 0:
            total_at_max = fixed + maximum
            profit_at_max = net - total_at_max - max(Decimal(0), total_at_max - equity) * interest_rate
            if profit_at_max <= equity * target:
                maximum -= Decimal('.01')
        scenarios[name] = dict(sale_price=str(revenue), construction=str(build), months=months,
                               commission=str(revenue - net), taxes=str(tax), liens=str(lien),
                               other_expenses='17000', finance_cost=str(interest), profit=str(profit),
                               roi=str(roi), modeled_maximum=str(maximum) if maximum >= 0 else None)
    return scenarios


def audit(row, modules, inventory):
    issues = [f'{name}:UNKNOWN' for name, item in modules.items() if item['status'] == UNKNOWN]
    exclusions = []
    flags = set(row.get('flags', []))
    listing, parcel, build, flood, title = (modules[name]['data'] for name in ('A1', 'A2', 'A4', 'A5', 'A6'))
    if listing['sale_status'] in {'CANCELLED', 'CANCELED', 'WITHDRAWN', 'SOLD'}:
        exclusions.append('UNAVAILABLE')
    if 'FRACTIONAL_INTEREST' in flags:
        exclusions.append('FRACTIONAL_INTEREST')
    if 'SPECIAL_PROCEEDING' in flags:
        issues.append('SPECIAL_PROCEEDING')
    location = ' '.join(str(value or '') for value in (row.get('address'), row.get('address_raw'), parcel['city']))
    if re.search(r'\bBAYTOWN\b', location, re.I):
        exclusions.append('BAYTOWN')
    if parcel['homestead_conflict']:
        issues.append('CONFLICTING_HOMESTEAD_EVIDENCE')
    if parcel['homestead'] is True:
        exclusions.append('HOMESTEAD')
    if parcel['vacant'] is False:
        exclusions.append('IMPROVED_OR_OCCUPIED')
    lot_sf = amount(parcel['lot_sf'])
    if lot_sf is not None and lot_sf < 5000:
        exclusions.append('BELOW_5000_SF')
    if any(build.get(key) is False for key in ('duplex_allowed', 'legal_access', 'buildable', 'restrictions_clear')):
        issues.append('CONSTRUCTION_REVIEW')
    if flood['sfha'] or flood['floodway'] or flood['maapnext_clear'] is False:
        issues.append('FLOOD_REVIEW')
    if title.get('title_clear') is False or title.get('redemption_resolved') is False:
        issues.append('TITLE_OR_REDEMPTION_REVIEW')
    if not inventory['reconciled']:
        issues.append('OFFICIAL_ROSTER_RECONCILIATION')
    comps = modules['A3']
    if comps['status'] == 'OBSERVED' and Decimal(comps['data']['median_price_psf']) < 165:
        issues.append('BASE_EXIT_ABOVE_COMPARABLE_MEDIAN')
    scenarios = modules['A8']['data']
    if scenarios and Decimal(scenarios['base']['roi']) <= Decimal('.20'):
        exclusions.append('BASE_ROI_AT_OR_BELOW_TARGET')
    if scenarios and Decimal(scenarios['downside']['profit']) < 0:
        issues.append('DOWNSIDE_LOSS')
    return dict(status='REVIEW' if issues or exclusions else 'PASSED', issues=issues, exclusions=exclusions)


def evaluate(row, bundle, inventory):
    account = row['account']
    modules = {
        'A1': a1(row, inventory),
        'A2': a2(row, bundle),
        'A3': observation(bundle, 'comparables', account, comparable_sales),
        'A4': observation(bundle, 'construction', account,
                          lambda data: boolean_fields(data, ('buildable', 'legal_access', 'restrictions_clear',
                                                            'duplex_allowed'))),
        'A5': a5(row, bundle),
        'A6': observation(bundle, 'title', account,
                          lambda data: boolean_fields(data, ('title_clear', 'redemption_resolved')) and
                          amount(data.get('liens_due')) is not None),
        'A7': observation(bundle, 'post_judgment_tax', account,
                          lambda data: amount(data.get('amount_due')) is not None and
                          bool(row.get('judgment_date')) and data.get('judgment_date') == row['judgment_date'] and
                          data.get('through_sale_date') == SALE_DATE),
    }
    comps = modules['A3']
    if comps['status'] == 'OBSERVED':
        prices = [amount(sale['price']) / amount(sale['building_sf']) for sale in comps['data']['sales']]
        comps['data'] = dict(comps['data'], median_price_psf=str(median(prices)))
    scenarios = None
    if modules['A6']['status'] == modules['A7']['status'] == 'OBSERVED':
        scenarios = finance(row.get('minimum_bid'), modules['A7']['data']['amount_due'],
                            modules['A6']['data']['liens_due'])
    modules['A8'] = status(scenarios is not None, scenarios, dict(
        project_sf=2600, equity='100000', target_roi='>0.20', annual_interest='0.12',
        commission='0.05', finance_method='SIMPLE_INTEREST_ON_PEAK_DEBT'))
    modules['A9'] = audit(row, modules, inventory)
    qa = modules['A9']
    action = 'NO_BID' if qa['exclusions'] else 'HOLD' if qa['issues'] else 'CANDIDATE'
    maximum = scenarios['base']['modeled_maximum'] if action == 'CANDIDATE' else None
    modules['A10'] = dict(status=action, maximum_bid=maximum, rank=None)
    return modules


def reconcile(document):
    rows = document['records']
    audit = document['audit']
    accounts = {row['account'] for row in rows}
    if not rows or len(accounts) != len(rows) or any(row['sale_date'] != SALE_DATE for row in rows):
        raise ValueError('Expected unique accounts from the December auction')
    if audit.get('sale_date') != SALE_DATE:
        raise ValueError('Audit date differs from December auction')
    groups = {}
    for row in rows:
        if row.get('group_target'):
            groups.setdefault(row['group_target'], []).append(row['account'])
    missing = set(document.get('unresolved_missing', []))
    missing.update(change['account'] for change in document.get('changes', [])
                   if change['kind'] == 'MISSING_NEEDS_REVIEW')
    official = (audit.get('source') == SOURCE and audit.get('status') == 'PASSED'
                and audit.get('records') == len(rows) and
                bool(re.fullmatch(r'[a-f0-9]{64}', str(audit.get('sha256') or ''))))
    return dict(audit=audit, official=official, groups=groups,
                reconciled=official and len(rows) == REFERENCE_COUNT and not missing,
                reference_count=REFERENCE_COUNT, count=len(rows), delta=len(rows) - REFERENCE_COUNT,
                missing_accounts=sorted(missing), missing_group_targets=sorted(groups.keys() - accounts),
                status_counts=dict(Counter(row['sale_status'] for row in rows)))


def process(document, checkpoint_dir, evidence=None, batch_size=25):
    if batch_size < 1:
        raise ValueError('Batch size must be positive')
    evidence = {} if evidence is None else evidence
    if not isinstance(evidence, dict):
        raise ValueError('Evidence must be an object keyed by account')
    inventory = reconcile(document)
    rows = document['records']
    output = []
    resumed = 0
    context = digest(dict(version=VERSION, inventory=inventory))
    for offset in range(0, len(rows), batch_size):
        for row in rows[offset:offset + batch_size]:
            account = row['account']
            if not re.fullmatch(r'\d{13}', account):
                raise ValueError('Invalid account identifier')
            bundle = evidence.get(account, {})
            try:
                checkpoint = Path(checkpoint_dir) / account / (digest([context, row, bundle]) + '.json')
            except (TypeError, ValueError):
                checkpoint = None
            try:
                if checkpoint is None:
                    raise ValueError('Invalid checkpoint input')
                modules = json.loads(checkpoint.read_text(encoding='utf-8'))
                if set(modules) != {f'A{i}' for i in range(1, 11)}:
                    raise ValueError('Incomplete checkpoint')
                resumed += 1
            except (FileNotFoundError, ValueError):
                try:
                    modules = evaluate(row, bundle, inventory)
                except (AttributeError, KeyError, TypeError, ValueError, ArithmeticError) as exc:
                    modules = {f'A{i}': status(False) for i in range(1, 9)}
                    modules['A9'] = dict(status='ERROR', issues=[type(exc).__name__], exclusions=[])
                    modules['A10'] = dict(status='HOLD', maximum_bid=None, rank=None)
                else:
                    if checkpoint is not None:
                        atomic_json(checkpoint, modules)
            output.append(dict(row, modules=modules, action=modules['A10']['status']))
    candidates = sorted((r for r in output if r['action'] == 'CANDIDATE'), key=lambda r: (
        ZIP_PRIORITY.index(r['modules']['A2']['data']['zip'])
        if r['modules']['A2']['data']['zip'] in ZIP_PRIORITY else len(ZIP_PRIORITY),
        -Decimal(r['modules']['A8']['data']['base']['roi']), r['account']))
    for rank, row in enumerate(candidates, 1):
        row['modules']['A10']['rank'] = rank
    return dict(document, records=output, diligence=dict(
        inventory=inventory, checkpoint_hits=resumed,
        action_counts=dict(Counter(row['action'] for row in output)),
        module_counts={name: dict(Counter(row['modules'][name]['status'] for row in output))
                       for name in (f'A{i}' for i in range(1, 11))}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--hcad-exemptions', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--batch-size', type=int, default=25)
    args = parser.parse_args()
    document = json.loads(args.inventory.read_text(encoding='utf-8'))
    evidence = json.loads(args.evidence.read_text(encoding='utf-8')) if args.evidence else None
    if args.hcad_exemptions:
        from hcad_exemptions import attach
        document = attach(document, args.hcad_exemptions)
    result = process(document, args.out / 'checkpoints', evidence, args.batch_size)
    atomic_json(args.out / 'results.json', result)
    print(json.dumps(result['diligence']))


if __name__ == '__main__':
    main()
