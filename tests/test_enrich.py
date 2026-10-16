import unittest
from enrich import query, summarize


class EnrichmentTests(unittest.TestCase):
    def test_multiple_parcels_require_review(self):
        self.assertEqual(summarize([{}, {}])['status'], 'MULTIPLE_MATCHES')

    def test_no_match_not_assumed_safe(self):
        self.assertEqual(summarize([])['homestead_status'], 'UNKNOWN')

    def test_account_sql_input_validated_before_network(self):
        with self.assertRaises(ValueError):
            query(["1' OR 1=1"])

    def test_observations_preserve_zero_and_unknown(self):
        row = summarize([{'attributes': {'site_str_num': 0, 'site_str_name': 'TEST',
                         'land_sqft': 5000, 'bld_value': 0, 'tax_year': '2026'}}])
        self.assertTrue(row['address'].startswith('0 TEST'))
        self.assertEqual(row['building_value'], 0)
        self.assertEqual(row['homestead_status'], 'UNKNOWN')
