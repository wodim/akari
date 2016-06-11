from fnmatch import fnmatch
from hashlib import md5
from textwrap import fill
import os
import random

from wand.color import Color
from wand.drawing import Drawing
from wand.image import Image

from image_search import image_search
from twitter import api


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
    draw.text(0, 0, fill(caption, 23))
    draw(img)

    # and save
    sum = md5(bytearray(caption, encoding='utf-8')).hexdigest()
    filename = 'images/akari_{}.jpeg'.format(sum)
    img.save(filename=filename)

    img.close()
    akari_mask.close()

    return filename, caption


def akari_search(text):
    try:
        filename, source_url = image_search(text)
    except:
        raise

    caption = 'わぁい{0} あかり{1}大好き'.format(text, text)
    return akari_compose(filename, caption)


def akari_cron():
    # get a random line. will error out if there are none, which is okay.
    with open('pending.txt') as file:
        lines = [x for x in file.read().splitlines() if len(x) > 10]
        if not lines:
            return
        line = random.choice(lines)

    min, max = 1, 5
    words = line.split(' ')
    start = random.randint(0, len(words) - 1)
    length = random.randint(min, max)

    text = ' '.join(words[start:start+length])
    filename, caption = akari_search(text)

    api.update_with_media(filename, status=caption)

    # empty the file
    with open('pending.txt', 'w'):
        pass
