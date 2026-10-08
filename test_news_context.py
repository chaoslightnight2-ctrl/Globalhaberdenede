import unittest
from news_context import source_context

class NewsContextTests(unittest.TestCase):
    def test_late_update_and_lead_remain_in_a_bounded_real_source(self):
        source = 'İlk açıklamada yaralılar hastaneye kaldırıldı. ' + 'Diğer ayrıntılar açıklandı. ' * 190 + 'Son güncellemede bir kişi hayatını kaybetti.'
        context = source_context(source)
        self.assertIn('İlk açıklamada yaralılar hastaneye kaldırıldı.', context)
        self.assertIn('Son güncellemede bir kişi hayatını kaybetti.', context)
        self.assertLess(len(context), 3900)

    def test_short_source_is_not_rewritten(self):
        source = 'Kaynakta açıklanan gerçek sonuç.'
        self.assertEqual(source_context(source), source)

    def test_large_unstructured_source_is_not_cut_mid_claim(self):
        with self.assertRaisesRegex(ValueError, 'complete lead'):
            source_context('uzun tek cümle ' * 400)

if __name__ == '__main__':
    unittest.main()
