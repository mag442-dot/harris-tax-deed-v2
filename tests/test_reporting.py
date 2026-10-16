import unittest
from reporting import report_rows, publication_requests


def document(**extra):
    row = dict(account='0010000000001', sale_date='2026-11-03', sale_status='FOR SALE',
               action='RESEARCH', flags=[], hcad_gis={}, **extra)
    return {'records': [row], 'audit': {'source': 'https://example.test/listing'}}


class ReportingTests(unittest.TestCase):
    def test_baytown_excluded_without_removing_record(self):
        rows = report_rows(document(address='5315 BAYWAY DR BAYTOWN TX 77520'))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][3], 'NO_BID')

    def test_historical_warning_is_retained_and_blocks_research(self):
        rows = report_rows(document(), {'0010000000001': 'Multi-account shared cause'})
        self.assertEqual(rows[1][3], 'HOLD')
        self.assertIn('Multi-account', rows[1][21])

    def test_accounts_and_formula_like_text_are_strings(self):
        req = publication_requests(document(address='=1+1'), 456, 'V2 Inventory')[1]['updateCells']
        values = req['rows'][1]['values']
        self.assertEqual(values[0]['userEnteredValue'], {'stringValue': '0010000000001'})
        self.assertEqual(values[4]['userEnteredValue'], {'stringValue': '=1+1'})
        self.assertEqual(req['range']['endColumnIndex'], len(values))
