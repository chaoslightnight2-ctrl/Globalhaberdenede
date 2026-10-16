import ast
import copy
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import news_generation as generation

class PromptFirstTests(unittest.TestCase):
    def test_complete_package_goes_directly_to_tts_without_editor_or_proof(self):
        data = {'title': 'Düzcede yeni yol açıldı', 'hook': 'Düzcede yeni yol ulaşıma açıldı',
                'narration_parts': ['Belediye yeni yolu açtı', 'Sürücüler yeni güzergahı kullanabilecek'],
                'cta': 'Global Haber kanalına abone ol', 'description': 'Yeni yol açıldı Siz ne düşünüyorsunuz',
                'visual_query': 'city road opening', 'topic_bucket': 'transport_cities',
                'tags': ['yol', 'belediye', 'ulaşım', 'güzergah', 'şehir'], 'hashtags': ['yol', 'ulaşım']}
        item = {'title': 'Road', 'summary': 'The council opened the new road in Duzce.'}
        with patch.object(generation, 'chat_json', return_value=copy.deepcopy(data)) as request:
            result = generation.generate(item, types.SimpleNamespace(), 'Global Haber')
        request.assert_called_once()
        self.assertIn('Duzce', request.call_args.args[0])
        self.assertEqual(result, item['spoken_text'])
        self.assertEqual(item['youtube_hashtags'], '#shorts #yol #ulaşım')
        self.assertNotIn('editorial_review', item)
        self.assertNotIn('publication_approval', item)
        self.assertEqual(item['generation_mode'], 'prompt_first_v1')
        self.assertNotIn('suitable', request.call_args.kwargs['schema']['properties'])

    def test_upload_has_no_editorial_approval_dependency(self):
        tree = ast.parse(Path('quality_runtime.py').read_text(encoding='utf-8'))
        upload = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'upload_to_youtube')
        self.assertNotIn('verify_approved', ast.unparse(upload))
