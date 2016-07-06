import random

import tweepy

from akari import Akari
from config import config
from image_search import ImageSearchException
from translator import Translator, TranslatorException
from twitter import twitter
import utils


class StreamException(Exception):
    pass


class TwitterBot(tweepy.streaming.StreamListener):
    @utils.background
    def on_status(self, status):
        utils.logger.info('{id} - "{text}" by {screen_name} via {source}'
                          .format(id=status.id,
                                  text=utils.clean(status.text),
                                  screen_name=status.author.screen_name,
                                  source=status.source))

        # ignore yourself
        if status.author.screen_name == twitter.me.screen_name:
            return

        # ignore retweets
        if hasattr(status, 'retweeted_status'):
            return

        # if the sources whitelist is enabled, ignore those who aren't on it
        if len(config['twitter']['sources_whitelist']) > 0:
            if status.source not in config['twitter']['sources_whitelist']:
                return

        # if the blacklist is enabled, ignore those who aren't on it
        if len(config['twitter']['text_blacklist']) > 0:
            if any(x in status.text
                   for x in config['twitter']['text_blacklist']):
                return

        text = utils.clean(status.text, urls=True, replies=True,
                           rts=True)
        if text == '':
            return

        # ignore those who are not talking to you
        if not status.text.startswith('@' + twitter.me.screen_name):
            # store this status
            with open('pending.txt', 'a') as p_file:
                p_file.write(str(status.id) + ' ' + text + '\n')
            return

        # ignore people with less than X followers
        if status.author.followers_count < 50:
            utils.logger.info('Ignoring because of low follower count')
            return

        # check ratelimit
        rate_limit = utils.rate_limit.hit('twitter', 'global', 1, 5)
        if not rate_limit['allowed']:
            return

        try:
            if config['twitter']['auto_translate']['enabled']:
                lang_from = config['twitter']['auto_translate']['from']
                lang_to = config['twitter']['auto_translate']['to']
                try:
                    translator = Translator(text,
                                            lang_from=lang_from,
                                            lang_to=lang_to)
                    text = translator.translation
                except TranslatorException as e:
                    utils.logger.exception('Error translating.')

            akari = Akari(text)
            text = akari.caption
            image = akari.filename
        except ImageSearchException as e:
            utils.logger.exception('Error searching for an image')
            text = str(e)
            image = None
        except Exception as e:
            utils.logger.exception('Error composing the image')
            msgs = ('No te oigo...',
                    'Prueba de nuevo más tarde.',
                    'Espera un rato y lo vuelves a intentar.',
                    'Me pillas en un mal momento, mejor luego.')
            text = random.choice(msgs)
            image = 'out-of-service.gif'

        # start building a reply. prepend @nick of whoever we are replying to
        reply = '@' + status.author.screen_name
        if text:
            reply += ' ' + text

        # post it
        try:
            if image:
                reply = utils.ellipsis(reply,
                                       twitter.MAX_STATUS_WITH_MEDIA_LENGTH)
                twitter.api.update_with_media(image, status=reply,
                                              in_reply_to_status_id=status.id)
            else:
                reply = utils.ellipsis(reply, twitter.MAX_STATUS_LENGTH)
                twitter.api.update_status(reply,
                                          in_reply_to_status_id=status.id)
        except Exception as e:
            utils.logger.exception('Error posting.')

    def on_error(self, status_code):
        utils.logger.warning('An error has occured! Status code = {}'
                             .format(status_code))
        return True  # keep stream alive

    def on_timeout(self):
        print('Snoozing Zzzzzz')


if __name__ == '__main__':
    try:
        listener = TwitterBot()
        stream = tweepy.Stream(twitter.auth, listener)
        stream.userstream()
    except KeyboardInterrupt:
        pass
