from datetime import datetime
from fnmatch import fnmatch
from textwrap import fill
import os
import random

from wand.color import Color
from wand.drawing import Drawing
from wand.image import Image

from config import config
from image_search import ImageSearch
import utils


class Akari(object):
    def __init__(self, text):
        image = ImageSearch(text, max_size=10 * 1024 * 1024)
        # make hashtags searchable
        if text[0] == '#':
            text = ' ' + text
        self.compose(image.hash, text)

    def compose(self, hash, text):
        filename = utils.build_path(hash, 'original')
        with Image(filename=filename) as original:
            img = original.convert('png')

        akaris = [x for x in os.listdir('.') if fnmatch(x, 'akari-mask-*.png')]

        akari_mask = Image(filename=random.choice(akaris))

        # resize
        img.transform(resize='{}x{}^'.format(akari_mask.width,
                                             akari_mask.height))
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
        filename = utils.build_path(hash, 'akari')
        img.save(filename=filename)

        img.close()
        akari_mask.close()

        self.filename = filename
        self.caption = caption


def akari_cron():
    from twitter import twitter

    # get a random line. will error out if there are none, which is okay.
    with open('pending.txt') as file:
        ids = [int(x.split(' ')[0]) for x in file.read().splitlines()]

    # this function generates a score for each tweet
    def score(status):
        # number of favs
        favs = status.favorite_count
        # decay coefficient. promotes newer tweets to compensate for the lower
        # amount of favs they have received (fewer people have seen them, in
        # theory)
        diff = (datetime.utcnow() - status.created_at).total_seconds()
        decay_coeff = utils.decay(diff, 20 * 60, 3)
        # number of followers
        followers = status.user.followers_count
        if followers == 0:
            followers = 1
        return favs * decay_coeff / followers

    statuses = []
    for i in range(0, len(ids), 100):
        group = ids[i:i + 100]
        statuses.extend(tuple(twitter.api.statuses_lookup(group)))
    statuses = sorted(statuses, key=score, reverse=True)

    # generate a new caption and try to find an image for it 10 times before
    # giving up
    min_len = config['akari']['min_line_length']
    min_w, max_w = config['akari']['min_words'], config['akari']['max_words']
    for i in range(10):
        try:
            line = utils.clean(statuses[i].text, urls=True, replies=True,
                               rts=True)
            words = line.split(' ')

            for j in range(10):
                start = random.randint(0, len(words) - 1)
                length = random.randint(min_w, max_w)
                text = ' '.join(words[start:start + length])

                if len(text) >= min_len:
                    break

            akari = Akari(text)
            break
        except:
            continue

    # this will crash it there's no caption available thus far, that's fine,
    # as the amount of tries has been exceeded and there was nothing left to do
    # anyway.
    status = utils.ellipsis(akari.caption,
                            twitter.MAX_STATUS_WITH_MEDIA_LENGTH)
    twitter.api.update_with_media(akari.filename, status=status)

    # if a new caption has been successfully published, empty the file
    with open('pending.txt', 'w'):
        pass


# like akari_cron(), but it forces a certain caption to be published
def akari_publish(text):
    from twitter import twitter

    akari = Akari(text)
    status = utils.ellipsis(akari.caption,
                            twitter.MAX_STATUS_WITH_MEDIA_LENGTH)
    twitter.api.update_with_media(akari.filename, status=status)
