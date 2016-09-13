from datetime import datetime
from textwrap import fill
import os
import statistics
import string

from wand.color import Color
from wand.drawing import Drawing
from wand.image import Image

from image_search import ImageSearch
import utils


class AkariAnimationTooLargeException(Exception):
    pass


class AkariFailedToGenerateAkariException(Exception):
    pass


class AkariWandIsRetardedException(Exception):
    pass


class Akari(object):
    def __init__(self, text, type='still', shuffle_results=False, **kwargs):
        self.text = text
        self.caption = kwargs.get('caption', self.text)
        self.type = type if type in ('still', 'animation') else 'still'

        self.image_search = ImageSearch(self.text, shuffle_results)

        for i in range(10):
            try:
                self.compose()
                return
            except AkariAnimationTooLargeException:
                utils.logger.info('Composed an animation that is too big.')
                # find another image
                self.image_search = ImageSearch(self.text, shuffle_results)
                continue
            except AkariWandIsRetardedException:
                utils.logger.info('Wand failed to save the animation.')
                continue

        raise AkariFailedToGenerateAkariException('Could not generate an ' +
                                                  'image.')

    def compose(self):
        utils.logger.info('Starting to compose Akari...')

        # make hashtags searchable
        if self.text.startswith('#'):
            self.text = ' ' + self.text + ' '

        width, height = 800, 600

        filename = utils.build_path(self.image_search.hash, 'original')
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

        # generate an image with the caption text that will be applied
        # to each frame.
        caption = 'わぁい{0}あかり{0}大好き'.format(self.text)
        draw = Drawing()
        draw.font = 'rounded-mgenplus-1c-bold.ttf'
        draw.font_size = 50
        draw.fill_color = Color('#fff')
        draw.stroke_color = Color('#000')
        draw.stroke_width = 1
        draw.gravity = 'south'
        draw.text(0, 0, fill(caption, 20))

        for mask in masks:
            # take the background image
            this_frame = Image(bg_img)

            # put akari on top of it
            akari_frame = Image(filename=mask)
            this_frame.composite(akari_frame, left=0, top=0)

            # draw the caption on this frame
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
        filename = utils.build_path(self.image_search.hash, self.type)
        result.save(filename=filename)

        draw.destroy()
        result.close()
        bg_img.close()

        try:
            if os.path.getsize(filename) > 3072 * 1024:
                raise AkariAnimationTooLargeException('Composed an ' +
                                                      'animation that is ' +
                                                      'too big.')
        except FileNotFoundError:
            raise AkariWandIsRetardedException('Wand failed to save the ' +
                                               'animation.')

        utils.logger.info(('Akari composed and saved as "{filename}"'
                           .format(filename=filename)))
        self.filename = filename
        self.caption = caption


def akari_cron():
    from twitter import twitter

    ids = []
    # get a random line. will error out if there are none, which is okay.
    with open('pending.txt') as file:
        for line in file.read().splitlines():
            id, text = line.split(' ', 1)
            if len(text) < 50:
                ids.append(id)

    # this function generates a score for each tweet
    def score(status):
        # filter garbage. at least 70% of letters in the status must be
        # /a-zA-Z/
        clean_text = utils.clean(status.text, urls=True, replies=True,
                                 rts=True)
        meat = sum(c in string.ascii_letters for c in clean_text) or -1
        if meat / len(clean_text) < 0.7:
            return -1
        favs = status.favorite_count
        rts = status.retweet_count
        followers = status.user.followers_count
        if followers < 1 or followers < median:
            return -1
        else:
            # decay coefficient. promotes newer tweets to compensate for the
            # lower amount of favs they have received (fewer people have seen
            # them, in theory)
            diff = (datetime.utcnow() - status.created_at).total_seconds()
            decay_coeff = utils.decay(diff, 20 * 60, 3)
            return decay_coeff * (favs + rts * 0.5) / followers

    # 100 at a time is the max statuses_lookup() can do.
    statuses = []
    for i in range(0, len(ids), 100):
        group = ids[i:i + 100]
        statuses.extend(tuple(twitter.api.statuses_lookup(group)))
    median = statistics.median(status.user.followers_count
                               for status in statuses)
    statuses.sort(key=score, reverse=True)

    # try to generate an image for the first status. if that fails, keep
    # trying with the next one until you have succeeded or until you have
    # run out of attempts.
    for status in statuses[:10]:
        try:
            caption = utils.clean(status.text, urls=True, replies=True,
                                  rts=True)
            utils.logger.info('Posting "{caption}" from {tweet_id}'
                              .format(caption=caption,
                                      tweet_id=status.id))
            akari = Akari(caption, type='animation', shuffle_results=False)
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
def akari_publish(text, **kwargs):
    from twitter import twitter

    akari = Akari(text, **kwargs)
    twitter.post(status=akari.caption, media=akari.filename)
