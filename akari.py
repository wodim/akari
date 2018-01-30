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
from config import cfg
from image_search import (image_search, ImageSearchResult,
                          ImageSearchResultError)
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
        # make hashtags searchable
        if '#' in self.text:
            self.text = ' %s ' % self.text

        self.caption = caption if caption else self.text
        if type not in ('still', 'animation'):
            raise ValueError('Incorrect Akari type "%s"' % type)
        self.type = type

        self.override = cfg('image_search:override:list')
        self.limit_results = cfg('akari:limit_results:int')
        self.caption_type = cfg('akari:caption_type')

        if image_url:
            result = ImageSearchResult(image_url, 'overriden', 'overriden')
            results = [result]
        else:
            if self.override:
                results = image_search(random.choice(self.override))
                random.shuffle(results)
            else:
                results = image_search(self.text)

            if self.limit_results:
                results = results[:self.limit_results]
                if shuffle_results:
                    random.shuffle(results)
            else:
                # results are always shuffled if # of results is uncapped
                random.shuffle(results)

        for result in results:
            # first, download the result. if it fails, continue for the next
            try:
                result.download()
            except ImageSearchResultError as exc:
                utils.logger.info('Error downloading this result: %s', exc)
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

    @staticmethod
    def warmup():
        """fill the image caches for each frame"""
        frames = cfg('akari:frames')
        if frames:
            if not frames.endswith(os.sep):
                frames += os.sep
            if os.path.isdir(frames):
                frames = sorted([frames + x for x in os.listdir(frames)])
            else:
                frames = [frames]

            akari_frames = [Image(filename=x) for x in frames]
            width, height = akari_frames[0].width, akari_frames[0].height
        else:
            akari_frames = []
            width, height = 1600, 1200

        # cache all of this
        cache.set('akari:frames', akari_frames)
        cache.set('akari:width', width)
        cache.set('akari:height', height)

        utils.logger.warning('Akari initialised.')

    def compose(self, image):
        utils.logger.info('Starting to compose Akari...')

        if 'akari:frames' not in cache:
            # cache miss
            utils.logger.warning('Akari frames were not warmed up!')
            self.warmup()

        akari_frames = cache.get('akari:frames')
        self.width = cache.get('akari:width')
        self.height = cache.get('akari:height')

        if self.type == 'animation' and len(akari_frames) < 2:
            # if we were asked to generate an animation but there's only one
            # mask, then we're generating a still image
            self.type = 'still'
        elif self.type == 'still' and len(akari_frames) > 1:
            # if we were asked to generate a still image and there are several
            # masks, use only the first one
            akari_frames = [akari_frames[0]]

        # now, get the background image
        filename = image.filename
        with Image(filename=filename) as original:
            # if it's an animation, take only the first frame
            if original.animation:
                bg_img = Image(original.sequence[0])
            else:
                bg_img = Image(original)
        # remove the alpha channel, if any
        bg_img.alpha_channel = False
        # resize it
        bg_img.transform(resize='{}x{}^'.format(self.width, self.height))
        bg_img.crop(width=self.width, height=self.height, gravity='center')

        if self.text:
            # generate the drawing to be applied to each frame
            if self.caption_type == 'seinfeld':
                caption, drawing = self._caption_seinfeld()
            elif self.caption_type == 'sanandreas':
                caption, drawing = self._caption_sanandreas()
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
        if not akari_frames:
            # shortcut in case there's no mask
            this_frame = Image(bg_img)
            if drawing:
                drawing(this_frame)
            result = Image(this_frame)
            this_frame.close()

        # save the result
        filename = image.get_path(self.type)
        result.compression_quality = 100
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

    # word of caution: 2nd parameter of textwrap.fill previously depended on
    # the font size, which in turn depended on image width. that was wrong;
    # the amount of letters that fit in every row *remains constant* no matter
    # what the font size or the image size is because the relative width of
    # every character remains constant, since the size of text changes lineally
    # depending on the image width.

    def _caption_akari(self):
        caption = 'わぁい{0} あかり{0}大好き'.format(self.text)
        drawing = Drawing()
        drawing.font = 'assets/fonts/rounded-mgenplus-1c-bold.ttf'
        drawing.font_size = self.width / 15
        text = fill(caption, 23)
        drawing.gravity = 'south'
        drawing.text_interline_spacing = drawing.font_size / -5
        offset = max(self.width / 400, 2)
        # first the shadow
        drawing.translate(offset, -offset)
        drawing.fill_color = Color('#000')
        drawing.fill_opacity = 0.5
        drawing.text(0, 0, text)
        # then the text
        drawing.translate(-offset, offset)
        drawing.fill_color = Color('#fff')
        drawing.fill_opacity = 1.0
        drawing.stroke_color = Color('#000')
        drawing.stroke_width = max(self.width / 600, 1)
        drawing.text(0, 0, text)
        return caption, drawing

    def _caption_seinfeld(self):
        caption = self.text
        drawing = Drawing()
        drawing.font = 'assets/fonts/NimbusSanL-RegIta.otf'
        drawing.font_size = self.width / 14
        text = fill(caption, 25)
        drawing.fill_color = Color('#000')
        drawing.translate(10, self.height / 12)
        # the number of shadows depends on image width, with a min of 1
        shadows = max(int(self.width / 150), 1)
        for _ in range(shadows):
            drawing.translate(-1, 1)
            drawing.gravity = 'south'
            drawing.text(0, 0, text)
        drawing.fill_color = Color('#fff')
        drawing.text(0, 0, text)
        return caption, drawing

    def _caption_sanandreas(self):
        caption = self.text
        drawing = Drawing()
        drawing.font = 'assets/fonts/TwCenMTStd-ExtraBold.otf'
        drawing.font_size = self.width / 20
        drawing.text_interline_spacing = drawing.font_size / 5
        drawing.fill_opacity = 0.8
        drawing.gravity = 'south'
        text = fill(caption, 30)
        drawing.fill_color = Color('#000')
        offset = drawing.font_size / 12
        drawing.translate(offset, self.height / 15)
        drawing.text(0, 0, text)
        drawing.translate(-offset, offset)
        drawing.fill_color = Color('#eee')
        drawing.text(0, 0, text)
        return caption, drawing


def akari_cron():
    Akari.warmup()

    # if there's an override, try to post it, but if it fails, continue
    # normally.
    try:
        cron_override = cfg('twitter:cron_override')
        if cron_override and akari_cron_override(cron_override):
            return
    except Exception:
        pass

    from twitter import twitter

    ids = []
    # get a random line. will error out if there are none, which is okay.
    with open('pending.txt', errors='replace') as file:
        for line in file.read().splitlines():
            id_, text = line.split(' ', 1)

            # if the blacklist is enabled, ignore tweets that match it
            blacklist = cfg('twitter:text_blacklist:re_list')
            if any(x.search(text) for x in blacklist):
                continue

            # alright, this tweet is a candidate
            ids.append(id_)

    # this function generates a score for each tweet
    def score(status):
        favs = status.favorite_count
        rts = status.retweet_count
        followers = status.user.followers_count
        if followers == 0 or followers < median * 2.5:
            return -1

        # decay coefficient. promotes newer tweets to compensate for the
        # lower amount of favs they have received (fewer people have seen
        # them, in theory)
        diff = (datetime.utcnow() - status.created_at).total_seconds()
        score = utils.decay(diff, 15 * 60, 1.5)
        score *= (favs * 3 + rts) / followers

        # filter garbage. at least 80% of letters in the status must be
        # /a-zA-Z/, or there's a big penalty
        clean_text = utils.clean(status.text,
                                 urls=True, replies=True, rts=True)
        meat = sum(c in string.ascii_letters for c in clean_text) or -1
        # also, get the author's lang and filter him if it's not in the wl
        wl = cfg('twitter:cron_lang_whitelist:list')
        if (wl and status.user.lang not in wl) or meat / len(clean_text) < 0.8:
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
