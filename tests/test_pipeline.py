import tempfile
import unittest
from pathlib import Path
from pipeline import QualityError, changes, parse_listing, run


def fixture(account='0650070000133', bid=True, description='An undivided one-fourth (1/4) interest in Lot 133.'):
    header = 'Minimum Bid: $64,355.24' if bid else 'Sold with Account#'
    return f'''<h2>Sale Date: November 03, 2026</h2>
    <div>Account#: {account} Cause#: 201969598</div>
    <div>Adjudged Value: $72,334.00 {header}</div>
    <h4>2105 FIRNAT ST, HOUSTON, TX 77093-7209</h4>
    <table><tr><td>Precinct:</td><td>Precinct 1</td></tr>
    <tr><td>Sale#:</td><td>1</td></tr><tr><td>Type:</td><td>SALE</td></tr></table>
    <h4>Description</h4><p>{description}</p><button>Close</button>'''


class PipelineTests(unittest.TestCase):
    def test_address_description_money_and_leading_zero(self):
        row = parse_listing(fixture(), '2026-11-03', 1)[0]
        self.assertEqual(row['account'], '0650070000133')
        self.assertEqual(row['minimum_bid'], '64355.24')
        self.assertIn('FIRNAT', row['address'])
        self.assertIn('FRACTIONAL_INTEREST', row['flags'])
        self.assertEqual(row['action'], 'HOLD')

    def test_group_without_target_never_gets_free_bid(self):
        row = parse_listing(fixture(bid=False), '2026-11-03', 1)[0]
        self.assertIsNone(row['minimum_bid'])
        self.assertIsNone(row['group_target'])
        self.assertIn('GROUP_REVIEW', row['flags'])

    def test_wrong_date_empty_and_duplicates_block(self):
        for html, date, minimum in [(fixture(), '2026-12-01', 1),
                                    (fixture(), '2026-11-03', 50),
                                    (fixture() + fixture(), '2026-11-03', 1)]:
            with self.assertRaises(QualityError):
                parse_listing(html, date, minimum)

    def test_missing_is_not_cancelled(self):
        self.assertEqual(changes([{'account': '001'}], []),
                         [{'account': '001', 'kind': 'MISSING_NEEDS_REVIEW'}])

    def test_enrichment_does_not_create_false_listing_changes(self):
        self.assertEqual(changes([{'account': '001', 'hcad_gis': {'status': 'SOURCE_REPORTED'}}],
                                 [{'account': '001'}]), [])

    def test_failure_preserves_latest_and_records_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            first = run(fixture(), directory, '2026-11-03', 1)
            second = run(fixture(), directory, '2026-11-03', 1)
            self.assertEqual(second['changes'], [])
            path = Path(directory) / '2026-11-03/latest.json'
            before = path.read_bytes()
            with self.assertRaises(QualityError):
                run('<html>Access denied</html>', directory, '2026-11-03', 1)
            self.assertEqual(before, path.read_bytes())
            self.assertEqual(len(list((Path(directory) / 'runs').glob('*.json'))), 3)

    def test_no_bid_recommendations_without_due_diligence(self):
        row = parse_listing(fixture(description='Lot 133 in Block J.'), '2026-11-03', 1)[0]
        self.assertEqual(row['action'], 'RESEARCH')
        self.assertEqual(row['homestead_status'], 'UNKNOWN')
        self.assertEqual(row['flood_status'], 'UNKNOWN')

    def test_missing_address_does_not_borrow_next_property(self):
        first = fixture().replace('2105 FIRNAT ST, HOUSTON, TX 77093-7209', '')
        second = fixture(account='0650070000160').replace('FIRNAT', 'OTHER')
        rows = parse_listing(first + second, '2026-11-03', 1)
        self.assertIsNone(rows[0]['address'])
        self.assertEqual(rows[0]['action'], 'HOLD')
        self.assertIn('OTHER', rows[1]['address'])


if __name__ == '__main__':
    unittest.main()
