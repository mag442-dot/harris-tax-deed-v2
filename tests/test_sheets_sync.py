import unittest
from sheets_sync import historical_warnings, publish


class Response:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class WrongHeaderSession:
    def __init__(self):
        self.posts = 0

    def get(self, url, **kwargs):
        if '/values/' in url:
            return Response({'values': [['My private notes']]})
        return Response({'sheets': [{'properties': {'title': 'V2 Inventory', 'sheetId': 1}}]})

    def post(self, *args, **kwargs):
        self.posts += 1
        raise AssertionError('Must not write unrelated content')


class SyncTests(unittest.TestCase):
    def test_unrecognized_staging_contents_block_write(self):
        session = WrongHeaderSession()
        with self.assertRaises(ValueError):
            publish({'records': []}, 'id', session)
        self.assertEqual(session.posts, 0)

    def test_unknown_legacy_cells_do_not_become_facts(self):
        row = [''] * 24
        row[7], row[17] = '0010000000001', 'UNKNOWN'
        self.assertEqual(historical_warnings([[], row], []), {})

    def test_history_keeps_fractional_warning_and_disposition(self):
        delta = [[], ['0010000000001', '', '', '', '', '', '', 'undivided interest', '', '', '', 'HOLD/NO BID']]
        self.assertIn('undivided interest', historical_warnings([], delta)['0010000000001'])
