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
from twitter import api
import utils


def akari_compose(filename, caption):
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
    draw = Drawing()
    draw.font = 'rounded-mgenplus-1c-bold.ttf'
    draw.font_size = 50
    draw.fill_color = Color('#fff')
    draw.stroke_color = Color('#000')
    draw.gravity = 'south'
    draw.text(0, 0, fill(caption, akari_mask.width // 35))
    draw(img)

    # and save
    sum = md5(bytearray(caption, encoding='utf-8')).hexdigest()
    filename = 'images/akari_{}.jpeg'.format(sum)
    img.save(filename=filename)

    img.close()
    akari_mask.close()

    return filename, caption


def akari_search(text):
    filename, source_url = image_search(text, max_size=10 * 1024 * 1024)
    caption = 'わぁい{0} あかり{0}大好き'.format(text)
    return akari_compose(filename, caption)


def akari_cron():
    # get a random line. will error out if there are none, which is okay.
    with open('pending.txt') as file:
        min_len = config['akari']['min_line_length']
        lines = [x for x in file.read().splitlines() if len(x) > min_len]
        if not lines:
            return
        line = random.choice(lines)

    def new_caption():
        min, max = config['akari']['min_words'], config['akari']['max_words']
        words = line.split(' ')
        start = random.randint(0, len(words) - 1)
        length = random.randint(min, max)

        return ' '.join(words[start:start + length])

    # try to generate a new caption a few times before giving up
    for i in range(10):
        try:
            filename, caption = akari_search(new_caption())
        except:
            continue

    # this will crash it there's no caption available thus far, that's fine,
    # as the amount of tries has been exceeded and there was nothing left to do
    # anyway.
    status = utils.ellipsis(caption, utils.MAX_STATUS_WITH_MEDIA_LENGTH)
    api.update_with_media(filename, status=status)

    # empty the file
    with open('pending.txt', 'w'):
        pass


# like akari_cron(), but it forces a certain caption to be published
def akari_publish(text):
    filename, caption = akari_search(text)
    status = utils.ellipsis(caption, utils.MAX_STATUS_WITH_MEDIA_LENGTH)
    api.update_with_media(filename, status=status)
