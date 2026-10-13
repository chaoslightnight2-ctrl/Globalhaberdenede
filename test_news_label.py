from pathlib import Path
import unittest
from unittest.mock import patch
import news_label
import ast
import os
import types

FONT = next((path for path in (news_label.DEJAVU_BOLD, Path('C:/Windows/Fonts/arialbd.ttf'))
             if path.is_file()), None)


@unittest.skipUnless(FONT, 'Test font unavailable')
class DisclosureLabelTests(unittest.TestCase):
    def test_imagemagick_alias_resolves_to_real_file_and_renders_turkish(self):
        with patch.object(news_label, 'DEJAVU_BOLD', FONT):
            image = news_label.label_image('DejaVu-Sans-Bold')
        self.assertEqual(image.size, (440, 66))
        self.assertGreater(image.getchannel('R').getextrema()[1], 0)
        self.assertEqual(image.getchannel('A').getextrema(), (155, 255))

    def test_supplied_font_file_is_usable_without_an_alias(self):
        image = news_label.label_image(str(FONT))
        self.assertGreater(image.getchannel('R').getextrema()[1], 0)

    def test_missing_font_is_a_clear_error(self):
        with self.assertRaisesRegex(ValueError, 'font file unavailable'):
            news_label.label_image('font-that-does-not-exist.ttf')

    def test_actual_caption_wrapper_uses_configured_font_without_old_download_helper(self):
        tree = ast.parse(Path('quality_runtime.py').read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == 'labelled_captions')
        def unused_download():
            self.fail('Disclosure must not use the old downloadable caption font')
        namespace = {'os': os, 'bot': types.SimpleNamespace(ensure_font=unused_download),
                     '_original_captions': lambda chunks: []}
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'quality_runtime.py', 'exec'), namespace)
        with patch.dict(os.environ, {'SUBTITLE_FONT': str(FONT)}):
            clips = namespace['labelled_captions']([(0, 1, 'Türkçe açıklama')])
        self.assertEqual(len(clips), 1)
        self.assertEqual(clips[0].duration, 1)
        self.assertEqual(clips[0].get_frame(0).shape[:2], (66, 440))
        clips[0].close()

if __name__ == '__main__':
    unittest.main()
