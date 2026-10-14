import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('public_receipt_probe', Path('maintenance/verify_public_receipts.py'))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class PublicReceiptsTests(unittest.TestCase):
    def test_reads_only_public_metadata_and_does_not_claim_missing_private_videos(self):
        service = Mock()
        service.videos.return_value.list.return_value.execute.return_value = {'items': [{
            'id': probe.QUIZ_IDS[0], 'snippet': {'channelId': probe.QUIZ_CHANNEL, 'title': 'Actual title'},
            'status': {'privacyStatus': 'public', 'uploadStatus': 'processed'}}]}
        report = probe.check(service)
        self.assertEqual(report['public_count'], 1)
        self.assertEqual([row['publication_status'] for row in report['videos']],
                         ['public_verified', 'not_publicly_verified', 'not_publicly_verified'])
        service.videos.return_value.list.assert_called_once_with(part='snippet,status', id=','.join(probe.QUIZ_IDS))
        service.videos.return_value.insert.assert_not_called()

    def test_wrong_channel_is_not_publication_proof(self):
        service = Mock()
        service.videos.return_value.list.return_value.execute.return_value = {'items': [{
            'id': probe.QUIZ_IDS[0], 'snippet': {'channelId': 'other', 'title': 'Other'},
            'status': {'privacyStatus': 'public'}}]}
        with self.assertRaisesRegex(ValueError, 'different channel'):
            probe.check(service)
