from pathlib import Path
import unittest
from unittest.mock import patch
import news_label

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

if __name__ == '__main__':
    unittest.main()
