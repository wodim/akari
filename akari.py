from datetime import datetime
from textwrap import fill
import os
import random

from wand.color import Color
from wand.drawing import Drawing
from wand.image import Image

from image_search import ImageSearch
import utils


class Akari(object):
    def __init__(self, text):
        image = ImageSearch(text, max_size=10 * 1024 * 1024)
        # make hashtags searchable
        if text[0] == '#':
            text = ' ' + text

        width, height = 800, 600

        filename = utils.build_path(image.hash, 'original')
        with Image(filename=filename) as original:
            if original.animation:
                bg_img = Image(original.sequence[0])
            else:
                bg_img = Image(original)

        bg_img.alpha_channel = False
        # resize
        bg_img.transform(resize='{}x{}^'.format(width, height))
        bg_img.crop(width=width, height=height, gravity='center')

        frames = sorted(['frames/' + x for x in os.listdir('frames')])
        gif = Image()

        for frame in frames:
            this_frame = Image(bg_img)

            # put akari on top
            akari_frame = Image(filename=frame)
            this_frame.composite(akari_frame, left=0, top=0)

            # text on top
            caption = 'わぁい{0} あかり{0}大好き'.format(text)
            draw = Drawing()
            draw.font = 'rounded-mgenplus-1c-bold.ttf'
            draw.font_size = 50
            draw.fill_color = Color('#fff')
            draw.stroke_color = Color('#000')
            draw.stroke_width = 1
            draw.gravity = 'south'
            draw.text(0, 0, fill(caption, 18))
            draw(this_frame)

            gif.sequence.append(this_frame)
            with gif.sequence[-1]:
                gif.sequence[-1].delay = 10
            this_frame.destroy()

        # and save
        filename = utils.build_path(image.hash, 'animation')
        gif.save(filename=filename)

        gif.close()
        bg_img.close()

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

    # 100 at a time is the max statuses_lookup() can do.
    statuses = []
    for i in range(0, len(ids), 100):
        group = ids[i:i + 100]
        statuses.extend(tuple(twitter.api.statuses_lookup(group)))
    statuses = sorted(statuses, key=score, reverse=True)

    # tweets shorter than this will be posted verbatim
    max_verbatim = 50

    # generate a new caption and try to find an image for it 10 times before
    # giving up
    for i in range(10):
        try:
            line = utils.clean(statuses[i].text, urls=True, replies=True,
                               rts=True)

            if len(line) <= max_verbatim:
                caption = line
            else:
                words = line.split(' ')
                # try to generate something longer than 2 characters 10 times,
                # if not, let it through
                for j in range(10):
                    start = random.randint(0, len(words) - 1)
                    length = random.randint(1, 10)
                    caption = ' '.join(words[start:start + length])

                    if len(caption) >= 2:
                        break

            utils.logger.info('Posting "{caption}" from {tweet_id}'
                              .format(caption=caption,
                                      tweet_id=statuses[i].id))
            akari = Akari(caption)
            break
        except:
            continue

    # this will crash it there's no caption available thus far, that's fine,
    # as the amount of tries has been exceeded and there was nothing left to do
    # anyway.
    twitter.post(status=akari.caption, media=akari.filename)

    # if a new caption has been successfully published, empty the file
    with open('pending.txt', 'w'):
        pass


# like akari_cron(), but it forces a certain caption to be published
def akari_publish(text):
    from twitter import twitter

    akari = Akari(text)
    twitter.post(status=akari.caption, media=akari.filename)
