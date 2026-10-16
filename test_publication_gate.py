import ast
import copy
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import Mock
import news_generation as generation
from source_review import make_proof


class PublicationGateTests(unittest.TestCase):
    def approved(self):
        source = 'The council opened the new road in Duzce.'
        item = {'title': 'Düzcede yeni yol açıldı', 'quality_hook': 'Düzcede açılan yeni yol kimi ilgilendiriyor',
                'quality_narration_parts': ['Belediye Düzcede yeni yolu açtı'],
                'youtube_description': 'Düzcede yeni yol açıldı', 'spoken_text': 'Onaylı konuşma',
                'tts_text': 'Onaylı konuşma.', 'youtube_tags': ['yol'], 'youtube_hashtags': '#shorts #yol #Düzce',
                'visual_query': 'city road opening', 'model_source_context': source, 'article_text': source}
        fields = generation.news_fields(item['title'], item['quality_hook'], item['quality_narration_parts'], item['youtube_description'])
        review = {'valid': True, 'reason': 'structural fixture only', 'evidence': [
            {'field': key, 'supported': True, 'source_quote': source} for key in fields]}
        item['editorial_review'] = review
        item['publication_approval'] = make_proof(generation.news_payload(item), fields, source, review)
        return item

    def test_upload_gateway_rejects_unreviewed_or_modified_text_before_media_and_oauth(self):
        tree = ast.parse(Path('quality_runtime.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'upload_to_youtube')
        render, bot = Mock(), Mock()
        namespace = {'validate_rendered_video': render, 'bot': bot}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'quality_runtime.py', 'exec'), namespace)
        approved = self.approved()
        generation.verify_approved_item(approved)
        changed = copy.deepcopy(approved)
        changed['youtube_description'] = 'Üsküdarda yol açıldı'
        for item in ({}, changed, dict(approved, script='Değiştirilmiş ses')):
            with self.subTest(item=item), self.assertRaises(ValueError):
                namespace['upload_to_youtube'](Path('nonexistent.mp4'), item, datetime.now(timezone.utc))
        render.assert_not_called()
        bot.get_youtube_service.assert_not_called()

    def test_explanation_cannot_be_omitted_from_approval(self):
        approved = self.approved()
        approved['editorial_review']['evidence'] = [row for row in approved['editorial_review']['evidence'] if row['field'] != 'description']
        with self.assertRaises(ValueError):
            generation.verify_approved_item(approved)
