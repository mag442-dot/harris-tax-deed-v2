import unittest
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch
from flood import summarize, query, enrich_flood


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

    def test_recent_matching_geometry_resumes_without_network(self):
        row = {'account': '0010000000001', 'hcad_gis': {'geometry': {'rings': [[[-95, 30]] * 4]}}}
        observed = {'status': 'INTERSECTION_OBSERVED', 'retrieved_at': datetime.now(timezone.utc).isoformat()}
        previous = {'records': [dict(row, fema=observed)]}
        with tempfile.TemporaryDirectory() as directory, patch('flood.query') as network:
            counts = enrich_flood({'records': [row]}, directory, previous=previous)
            network.assert_not_called()
        self.assertEqual(counts, {'INTERSECTION_OBSERVED': 1})
