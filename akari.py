from datetime import datetime
from textwrap import fill
import os

from wand.color import Color
from wand.drawing import Drawing
from wand.image import Image

from image_search import ImageSearch
import utils


class AkariAnimationTooLargeException(Exception):
    pass


class AkariFailedToGenerateAkariException(Exception):
    pass


class Akari(object):
    def __init__(self, text, type='still'):
        self.text = text
        self.type = type

        for i in range(10):
            try:
                self.compose()
                return
            except AkariAnimationTooLargeException as e:
                utils.logger.info('Composed an animation that is too big.')
                continue

        raise AkariFailedToGenerateAkariException('Could not generate an ' +
                                                  'image.')

    def compose(self):
        image = ImageSearch(self.text, max_size=10 * 1024 * 1024)
        # make hashtags searchable
        if self.text[0] == '#':
            self.text = ' ' + self.text

        width, height = 800, 600

        filename = utils.build_path(image.hash, 'original')
        with Image(filename=filename) as original:
            # if it's an animation, take only the first frame
            if original.animation:
                bg_img = Image(original.sequence[0])
            else:
                bg_img = Image(original)

        # remove the alpha channel
        bg_img.alpha_channel = False

        # resize
        bg_img.transform(resize='{}x{}^'.format(width, height))
        bg_img.crop(width=width, height=height, gravity='center')

        if self.type == 'still':
            masks = ('masks/still.png',)
        elif self.type == 'animation':
            masks = sorted(['frames/' + x for x in os.listdir('frames')])
            # this will be the image we will append the frames to
            result = Image()

        for mask in masks:
            # take the background image
            this_frame = Image(bg_img)

            # put akari on top of it
            akari_frame = Image(filename=mask)
            this_frame.composite(akari_frame, left=0, top=0)

            # then the caption on top of it
            caption = 'わぁい{0} あかり{0}大好き'.format(self.text)
            draw = Drawing()
            draw.font = 'rounded-mgenplus-1c-bold.ttf'
            draw.font_size = 50
            draw.fill_color = Color('#fff')
            draw.stroke_color = Color('#000')
            draw.stroke_width = 1
            draw.gravity = 'south'
            draw.text(0, 0, fill(caption, 20))
            draw(this_frame)

            if self.type == 'still':
                # we are done already
                result = Image(this_frame)
            elif self.type == 'animation':
                # add the frame to the result image
                result.sequence.append(this_frame)
                with result.sequence[-1]:
                    result.sequence[-1].delay = 10

            akari_frame.close()
            this_frame.close()

        # save the result
        filename = utils.build_path(image.hash, self.type)
        result.save(filename=filename)

        result.close()
        bg_img.close()

        if os.path.getsize(filename) > 3072 * 1024:
            raise AkariAnimationTooLargeException('Composed an animation ' +
                                                  'that is too big.')

        self.filename = filename
        self.caption = caption


def akari_cron():
    from twitter import twitter

    # get a random line. will error out if there are none, which is okay.
    with open('pending.txt') as file:
        ids = [int(x.split(' ')[0]) for x in file.read().splitlines()]

    # this function generates a score for each tweet
    def score(status):
        favs, followers = status.favorite_count, status.user.followers_count
        # decay coefficient. promotes newer tweets to compensate for the lower
        # amount of favs they have received (fewer people have seen them, in
        # theory)
        diff = (datetime.utcnow() - status.created_at).total_seconds()
        decay_coeff = utils.decay(diff, 20 * 60, 3)
        return decay_coeff * favs / followers

    # 100 at a time is the max statuses_lookup() can do.
    statuses = []
    for i in range(0, len(ids), 100):
        group = ids[i:i + 100]
        statuses.extend(tuple(twitter.api.statuses_lookup(group)))
    statuses = sorted(statuses, key=score, reverse=True)

    # tweets shorter than this will be posted verbatim
    max_verbatim = 50

    # generate a new caption and try to find an image for each status
    for status in statuses:
        try:
            caption = utils.clean(status.text, urls=True, replies=True,
                                  rts=True)

            if len(caption) <= max_verbatim:
                utils.logger.info('Posting "{caption}" from {tweet_id}'
                                  .format(caption=caption,
                                          tweet_id=status.id))
                akari = Akari(caption, type='animation')
                break
        except:
            utils.logger.exception('Error generating a caption.')
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

    akari = Akari(text, type='animation')
    twitter.post(status=akari.caption, media=akari.filename)
