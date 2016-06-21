from fnmatch import fnmatch
from hashlib import md5
from textwrap import fill
import os
import random

from wand.color import Color
from wand.drawing import Drawing
from wand.image import Image

from config import config
from image_search import image_search
import utils


def akari_compose(filename, text):
    with Image(filename=filename) as original:
        img = original.convert('png')

    akaris = [x for x in os.listdir('.') if fnmatch(x, 'akari-mask-*.png')]

    akari_mask = Image(filename=random.choice(akaris))

    # resize
    img.transform(resize='{}x{}^'.format(akari_mask.width, akari_mask.height))
    img.crop(width=akari_mask.width, height=akari_mask.height,
             gravity='center')

    # put akari on top
    img.composite(akari_mask, left=0, top=0)

    # text on top
    caption = 'わぁい{0} あかり{0}大好き'.format(text)
    draw = Drawing()
    draw.font = 'rounded-mgenplus-1c-bold.ttf'
    draw.font_size = 100
    draw.fill_color = Color('#fff')
    draw.stroke_color = Color('#000')
    draw.stroke_width = 2
    draw.gravity = 'south'
    draw.text(0, 0, fill(caption, int(draw.font_size // 5)))
    draw(img)

    # and save
    md5sum = md5(bytearray(text, encoding='utf-8')).hexdigest()
    filename = 'images/image_{}_akari.jpeg'.format(md5sum)
    img.save(filename=filename)

    img.close()
    akari_mask.close()

    return filename, caption


def akari_search(text):
    filename, source_url = image_search(text, max_size=10 * 1024 * 1024)
    # make hashtags searchable
    if text[0] == '#':
        text = ' ' + text
    return akari_compose(filename, text)


def akari_cron():
    # get a random line. will error out if there are none, which is okay.
    with open('pending.txt') as file:
        min_len = config['akari']['min_line_length']
        lines = [x for x in file.read().splitlines() if len(x) >= min_len]
        if not lines:
            # return if there is nothing useful in the queue yet.
            return

    def new_caption():
        # try to generate a new caption of at least 10 characters at least
        # 10 times before giving up and letting anything through
        min, max = config['akari']['min_words'], config['akari']['max_words']
        line = random.choice(lines)
        words = line.split(' ')
        for i in range(10):
            start = random.randint(0, len(words) - 1)
            length = random.randint(min, max)
            text = ' '.join(words[start:start + length])

            if len(text) >= 4:
                break

        return text

    # generate a new caption and try to find an image for it 10 times before
    # giving up
    for i in range(10):
        try:
            filename, caption = akari_search(new_caption())
            break
        except:
            continue

    # this will crash it there's no caption available thus far, that's fine,
    # as the amount of tries has been exceeded and there was nothing left to do
    # anyway.
    from twitter import api

    status = utils.ellipsis(caption, utils.MAX_STATUS_WITH_MEDIA_LENGTH)
    api.update_with_media(filename, status=status)

    # if a new caption has been successfully published, empty the file
    with open('pending.txt', 'w'):
        pass


# like akari_cron(), but it forces a certain caption to be published
def akari_publish(text):
    from twitter import api

    filename, caption = akari_search(text)
    status = utils.ellipsis(caption, utils.MAX_STATUS_WITH_MEDIA_LENGTH)
    api.update_with_media(filename, status=status)
