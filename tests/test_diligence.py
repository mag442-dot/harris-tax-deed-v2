import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from diligence import SALE_DATE, finance, process
from diligence_sheet import TAB, requests_for, rows
from pipeline import SOURCE


def proof(account, **data):
    return dict(account=account, sale_date=SALE_DATE, data=data, observed_on='2026-11-23',
                source='https://example.test/records', reference='fixture')


def inputs():
    records = []
    for index in range(157):
        account = str(index).zfill(13)
        records.append(dict(account=account, sale_date=SALE_DATE, sale_status='FOR SALE',
                            address='0 Main St Houston TX 77028', minimum_bid='1500',
                            legal_description='LOT 1', judgment_date='07/01/2026', cause='100', precinct='1', sale_number='1',
                            hcad_gis=dict(status='SOURCE_REPORTED', city='Houston', zip='77028',
                                          source='https://example.test/gis', lot_sf=5000,
                                          state_class='C1', building_value=0),
                            fema=dict(status='INTERSECTION_OBSERVED', sfha_intersects=None,
                                      floodway_intersects=None, source='https://example.test/fema')))
    first = records[0]['account']
    evidence = {first: dict(
        hcad=proof(first, homestead=False, vacant=True),
        comparables=proof(first, sales=[
            dict(property_type='DUPLEX', closed=True, price=429000, building_sf=2600,
                 reference=str(idx), closed_on='2026-10-01') for idx in range(3)]),
        construction=proof(first, buildable=True, legal_access=True, restrictions_clear=True,
                           duplex_allowed=True),
        maapnext=proof(first, development_clear=True),
        fema_review=proof(first, coverage_verified=True, sfha_intersects=False, floodway_intersects=False),
        title=proof(first, title_clear=True, redemption_resolved=True, liens_due=0),
        post_judgment_tax=proof(first, amount_due=0, judgment_date='07/01/2026', through_sale_date=SALE_DATE),
    )}
    return dict(records=records, audit=dict(sale_date=SALE_DATE, source=SOURCE, status='PASSED',
                                           records=157, sha256='a' * 64)), evidence


class DiligenceTest(unittest.TestCase):
    def test_finance_and_strict_threshold(self):
        scenario = finance('1500', 0, 0)['base']
        self.assertEqual(scenario['sale_price'], '429000')
        self.assertEqual(scenario['construction'], '273000')
        self.assertEqual(scenario['finance_cost'], '17235.00')
        self.assertEqual(scenario['profit'], '98815.00')
        from decimal import Decimal
        maximum = Decimal(scenario['modeled_maximum'])
        self.assertGreater(Decimal(finance(maximum, 0, 0)['base']['roi']), Decimal('.20'))
        self.assertLessEqual(Decimal(finance(maximum + Decimal('.01'), 0, 0)['base']['roi']), Decimal('.20'))
        self.assertIsNone(finance(1500, None, 0))
        self.assertIsNone(finance(1500, 'NaN', 0))

    def test_evidence_to_ranking_and_resume(self):
        document, evidence = inputs()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = process(document, root, evidence, batch_size=17)
            self.assertEqual(first['records'][0]['modules']['A10']['rank'], 1)
            self.assertEqual(first['records'][1]['action'], 'HOLD')
            self.assertEqual(first['records'][1]['modules']['A7']['status'], 'UNKNOWN')
            with patch('diligence.evaluate', side_effect=AssertionError('should resume')):
                self.assertEqual(process(document, root, evidence)['diligence']['checkpoint_hits'], 157)
            evidence[document['records'][0]['account']]['hcad']['data']['homestead'] = True
            revised = process(document, root, evidence)
            self.assertEqual(revised['diligence']['checkpoint_hits'], 156)
            self.assertEqual(revised['records'][0]['action'], 'NO_BID')
            self.assertIsNone(revised['records'][0]['modules']['A10']['maximum_bid'])

    def test_group_and_cancellation_and_malformed_property(self):
        document, evidence = inputs()
        first, second, third, fourth = document['records'][:4]
        second.update(grouped=True, group_target=first['account'])
        third.update(sale_status='CANCELLED')
        fourth.update(hcad_gis=None)
        with tempfile.TemporaryDirectory() as directory:
            result = process(document, directory, evidence)
        rows_by_account = {row['account']: row for row in result['records']}
        self.assertEqual(rows_by_account[first['account']]['action'], 'HOLD')
        self.assertEqual(rows_by_account[second['account']]['modules']['A1']['status'], 'UNKNOWN')
        self.assertEqual(rows_by_account[third['account']]['action'], 'NO_BID')
        self.assertEqual(rows_by_account[fourth['account']]['modules']['A9']['status'], 'ERROR')
        self.assertEqual(len(result['records']), 157)

    def test_reconciliation_and_sheet_shape(self):
        document, evidence = inputs()
        document['changes'] = [dict(account='9000000000000', kind='MISSING_NEEDS_REVIEW')]
        with tempfile.TemporaryDirectory() as directory:
            result = process(document, directory, evidence)
        self.assertFalse(result['diligence']['inventory']['reconciled'])
        self.assertEqual(result['records'][0]['action'], 'HOLD')
        matrix = rows(result)
        self.assertEqual(len(matrix), 158)
        self.assertTrue(all(len(row) == 25 for row in matrix))
        requests = requests_for(matrix, 123)
        self.assertEqual(requests[0]['addSheet']['properties']['title'], TAB)
        self.assertEqual(requests[1]['updateCells']['rows'][1]['values'][0],
                         {'userEnteredValue': {'stringValue': '0000000000000'}})


if __name__ == '__main__':
    unittest.main()
