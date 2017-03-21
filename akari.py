from datetime import datetime
from textwrap import fill
import os
import random
import statistics
import string

from wand.color import Color
from wand.drawing import Drawing
from wand.image import Image

from cache import cache
from config import config
from image_search import ImageSearch, ImageSearchResult, ImageSearchResultError
import utils


class AkariTooBigError(Exception):
    pass


class AkariComposingError(Exception):
    pass


class AkariWandIsRetardedError(Exception):
    pass


class Akari(object):
    def __init__(self, text, type='still', shuffle_results=False,
                 caption=None, image_url=None):
        self.text = text
        self.caption = caption if caption else self.text
        if type not in ('still', 'animation'):
            raise ValueError('Incorrect Akari type "%s"' % type)
        self.type = type

        if image_url:
            result = ImageSearchResult(image_url, 'overriden', 'overriden')
            results = [result]
        else:
            results = ImageSearch(self.text).results[:5]
            try:
                limit_results = config.get('akari', 'limit_results', type=int)
                results = results[:limit_results]
                # results are always shuffled if # of results is capped
                random.shuffle(results)
            except KeyError:
                if shuffle_results:
                    random.shuffle(results)
                pass

        for result in results:
            # first, download the result. if it fails, continue for the next
            try:
                result.download()
            except ImageSearchResultError as exc:
                utils.logger.info('Error downloading this result: ' + str(exc))
                continue

            # then, compose it. 3 tries, in case Wand acts funny.
            for _ in range(3):
                try:
                    self.compose(result)
                    return
                except AkariTooBigError:
                    utils.logger.info('Composed an animation that is too big.')
                    # a retry would generate the same gif with the same
                    # problem, so don't do that. go for the next result.
                    break
                except AkariWandIsRetardedError:
                    # this, we want to retry it
                    utils.logger.info('Wand failed to save the animation.')

        raise AkariComposingError('Could not generate an image.')

    def compose(self, image):
        utils.logger.info('Starting to compose Akari...')

        # make hashtags searchable
        if '#' in self.text:
            self.text = ' ' + self.text + ' '

        # try to get all masks from cache
        akari_frames = cache.get('akari_frames:%s' % self.type)

        if not akari_frames:  # cache miss
            masks = config.get('akari', 'frames')
            if os.path.isdir(masks):
                masks = sorted([masks + x for x in os.listdir(masks)])
            else:
                masks = [masks]

            # generate the list of masks
            if self.type == 'still':
                masks = masks[0]
            elif self.type == 'animation':
                # if there's only one frame here, it's not an animation
                if len(masks) == 1:
                    self.type = 'still'
            akari_frames = [Image(filename=x) for x in masks]

            # cache all of this
            cache.set('akari_frames:%s' % self.type, akari_frames)

        width, height = akari_frames[0].width, akari_frames[0].height

        # now, get the background image
        filename = image.get_path('original')
        with Image(filename=filename) as original:
            # if it's an animation, take only the first frame
            if original.animation:
                bg_img = Image(original.sequence[0])
            else:
                bg_img = Image(original)
        # remove the alpha channel, if any
        bg_img.alpha_channel = False
        # resize it
        bg_img.transform(resize='{}x{}^'.format(width, height))
        bg_img.crop(width=width, height=height, gravity='center')

        if self.text:
            # generate the drawing to be applied to each frame
            if config.get('akari', 'caption_type') == 'seinfeld':
                caption, drawing = self._caption_seinfeld()
            else:
                caption, drawing = self._caption_akari()
        else:
            caption, drawing = '', None

        result = Image()  # this will be the resulting image
        for akari_frame in akari_frames:
            # take the background image
            this_frame = Image(bg_img)

            # put akari on top of it
            this_frame.composite(akari_frame, left=0, top=0)

            if drawing:
                # draw the caption on this frame
                drawing(this_frame)

            if len(akari_frames) == 1:
                # we are done already
                result = Image(this_frame)
            else:
                # add the frame to the result image
                result.sequence.append(this_frame)
                with result.sequence[-1]:
                    result.sequence[-1].delay = 10
            # remove this frame from memory (it's in the sequence already)
            this_frame.close()

        # save the result
        filename = image.get_path(self.type)
        result.save(filename=filename)

        # destroy everything
        if drawing:
            drawing.destroy()
        for frame in result.sequence:
            frame.destroy()
        result.close()
        bg_img.close()

        try:
            # if the gif is too big, it has to be discarded. a new one
            # will be generated using a different image this time.
            if os.path.getsize(filename) > 3072 * 1024:
                raise AkariTooBigError('Composed an animation that is too big')
        except FileNotFoundError:
            # sometimes Wand fails to save the animation, and does not even
            # raise an exception. retry in this case.
            raise AkariWandIsRetardedError('Wand failed to save the animation')

        utils.logger.info('Akari composed and saved as "%s"', filename)
        self.filename = filename
        self.caption = caption

    def _caption_akari(self):
        caption = 'わぁい{0} あかり{0}大好き'.format(self.text)
        drawing = Drawing()
        drawing.font = 'assets/fonts/rounded-mgenplus-1c-bold.ttf'
        drawing.font_size = 50
        drawing.gravity = 'south'
        drawing.text_interline_spacing = drawing.font_size / -5
        # first the shadow
        drawing.translate(3, -3)
        drawing.fill_color = Color('#000')
        drawing.fill_opacity = 0.5
        drawing.text(0, 0, fill(caption, 24))
        # then the text
        drawing.translate(-3, 3)
        drawing.fill_color = Color('#fff')
        drawing.fill_opacity = 1
        drawing.stroke_color = Color('#000')
        drawing.stroke_width = 1.5
        drawing.text(0, 0, fill(caption, 24))
        return caption, drawing

    def _caption_seinfeld(self):
        caption = self.text
        drawing = Drawing()
        drawing.font = 'assets/fonts/NimbusSanL-RegIta.otf'
        drawing.font_size = 90
        drawing.fill_color = Color('#000')
        drawing.translate(10, 100)
        for _ in range(8):
            drawing.translate(-1, 1)
            drawing.gravity = 'south'
            drawing.text(0, 0, fill(caption, int(drawing.font_size // 3)))
        drawing.fill_color = Color('#fff')
        drawing.text(0, 0, fill(caption, int(drawing.font_size // 3)))
        return caption, drawing


def akari_cron():
    # if there's an override, try to post it, but if it fails, continue
    # normally.
    try:
        cron_override = config.get('twitter', 'cron_override')
        if cron_override and akari_cron_override(cron_override):
            # remove it so it's not posted in loop
            config.set('twitter', 'cron_override', '')
            return
    except Exception:
        pass

    from twitter import twitter

    ids = []
    # get a random line. will error out if there are none, which is okay.
    with open('pending.txt') as file:
        for line in file.read().splitlines():
            id_, text = line.split(' ', 1)

            # if the blacklist is enabled, ignore tweets that match it
            blacklist = config.get('twitter', 'text_blacklist', type='re_list')
            if any(x.search(text) for x in blacklist):
                continue

            # alright, this tweet is a candidate
            ids.append(id_)

    # this function generates a score for each tweet
    def score(status):
        favs = status.favorite_count
        rts = status.retweet_count
        followers = status.user.followers_count
        if followers == 0 or followers < median * 1.5:
            return -1

        # decay coefficient. promotes newer tweets to compensate for the
        # lower amount of favs they have received (fewer people have seen
        # them, in theory)
        diff = (datetime.utcnow() - status.created_at).total_seconds()
        score = utils.decay(diff, 20 * 60, 1.5)
        score *= (favs + rts * 0.7) / followers

        # filter garbage. at least 80% of letters in the status must be
        # /a-zA-Z/, or there's a big penalty
        clean_text = utils.clean(status.text,
                                 urls=True, replies=True, rts=True)
        meat = sum(c in string.ascii_letters for c in clean_text) or -1
        if meat / len(clean_text) < 0.8:
            score /= 10

        return score

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
            caption = utils.clean(status.text,
                                  urls=True, replies=True, rts=True)
            utils.logger.info('Posting "%s" from %d', caption, status.id)
            akari = Akari(caption, type='animation', shuffle_results=False)
            break
        except Exception:
            utils.logger.exception('Error generating a caption.')
            continue

    # this will crash it there's no caption available thus far, that's fine,
    # as the amount of tries has been exceeded and there was nothing left to do
    # anyway.
    twitter.post(status=akari.caption, media=akari.filename)

    # if a new caption has been successfully published, empty the file
    with open('pending.txt', 'w'):
        pass


def akari_cron_override(caption):
    from twitter import twitter

    utils.logger.info('Overriding cron with "%s"!', caption)
    akari = Akari(caption, type='animation', shuffle_results=False)
    twitter.post(status=akari.caption, media=akari.filename)
    return True


# like akari_cron(), but it forces a certain caption to be published
def akari_publish(text, **kwargs):
    from twitter import twitter

    akari = Akari(text, **kwargs)
    twitter.post(status=akari.caption, media=akari.filename)
