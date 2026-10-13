"""Draw the stock-footage disclosure using an actual installed font file."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

DEJAVU_BOLD = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')


def label_image(preferred_font):
    path = Path(preferred_font)
    if not path.is_file() and preferred_font == 'DejaVu-Sans-Bold':
        # ImageMagick understands this alias; Pillow requires its installed file.
        path = DEJAVU_BOLD
    if not path.is_file():
        raise ValueError('Stock disclosure font file unavailable: ' + str(path))
    font = ImageFont.truetype(str(path), 30)
    canvas = Image.new('RGBA', (440, 66), (0, 0, 0, 155))
    ImageDraw.Draw(canvas).text((220, 33), 'Temsili görüntü', font=font,
                               fill='white', anchor='mm')
    return canvas
