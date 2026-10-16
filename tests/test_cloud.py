import json
import unittest
from pathlib import Path
from unittest.mock import patch
from cloud_job import execute


class Missing(Exception):
    pass


class Conflict(Exception):
    pass


class Blob:
    def __init__(self, bucket, name):
        self.bucket, self.name, self.generation = bucket, name, 7

    def reload(self):
        if self.name not in self.bucket.data:
            raise Missing()

    def download_as_text(self, **kwargs):
        return self.bucket.data[self.name]

    def upload_from_string(self, data, **kwargs):
        self.bucket.writes.append((self.name, kwargs.get('if_generation_match')))
        if self.bucket.conflict and self.name.endswith('/latest.json'):
            raise Conflict()
        self.bucket.data[self.name] = data


class Bucket:
    def __init__(self, conflict=False):
        self.data, self.writes, self.conflict = {}, [], conflict

    def blob(self, name):
        return Blob(self, name)


def fake_enrich(inventory, directory):
    directory.mkdir(parents=True)
    (directory / 'enriched.json').write_text(json.dumps(inventory))
    return {'SOURCE_REPORTED': 1}


class CloudTests(unittest.TestCase):
    @patch('cloud_job.enrich', side_effect=fake_enrich)
    @patch('cloud_job.run', return_value={'records': [{'account': '001'}]})
    @patch('cloud_job.fetch', return_value='<html/>')
    def test_create_pointer_requires_absence(self, *_):
        bucket = Bucket()
        execute(bucket, '2026-11-03', Missing, Conflict)
        self.assertEqual(bucket.writes[-1], ('sales/2026-11-03/latest.json', 0))

    @patch('cloud_job.enrich', side_effect=fake_enrich)
    @patch('cloud_job.run', return_value={'records': [{'account': '001'}]})
    @patch('cloud_job.fetch', return_value='<html/>')
    def test_concurrent_change_cannot_overwrite_pointer(self, *_):
        bucket = Bucket(conflict=True)
        key = 'sales/2026-11-03/latest.json'
        bucket.data[key] = '{"records": []}'
        with self.assertRaises(Conflict):
            execute(bucket, '2026-11-03', Missing, Conflict)
        self.assertEqual(bucket.data[key], '{"records": []}')
        self.assertIn((key, 7), bucket.writes)
        self.assertTrue(any(name.endswith('failure.json') for name in bucket.data))
