import unittest
from flood import summarize, query


class FloodTests(unittest.TestCase):
    def test_no_match_never_means_safe(self):
        r = summarize({'features': []})
        self.assertEqual(r['status'], 'NO_MATCH_REQUIRES_REVIEW')
        self.assertIsNone(r['sfha_intersects'])

    def test_observed_sfha_does_not_claim_area_coverage(self):
        r = summarize({'features': [{'attributes': {'FLD_ZONE': 'AE', 'SFHA_TF': 'T',
                                                   'ZONE_SUBTY': 'FLOODWAY'}}]})
        self.assertTrue(r['sfha_intersects'])
        self.assertTrue(r['floodway_intersects'])
        self.assertEqual(r['coverage_status'], 'NOT_MEASURED')

    def test_projected_coordinates_cannot_be_sent_as_latlon(self):
        with self.assertRaises(ValueError):
            query({'rings': [[[3000000, 13000000]] * 4]})
