import random

import tweepy

from akari import Akari
from config import config
from image_search import ImageSearchNoResultsException
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

        # if the blacklist is enabled, ignore tweets that match it
        if len(config['twitter']['text_blacklist']) > 0:
            if any(x.search(status.text)
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
        if status.author.followers_count < 25:
            utils.logger.info('Ignoring because of low follower count')
            return

        # check ratelimit
        rate_limit = utils.rate_limit.hit('twitter', 'global', 1, 3)
        if not rate_limit['allowed']:
            utils.logger.info('Ignoring because of ratelimit')
            return

        # follow the user if he's new. if he does not follow back, he'll
        # be unfollowed by followers.unfollow_my_unfollowers sometime later.
        if not status.author.following:
            try:
                utils.logger.info('Following this user back.')
                twitter.api.create_friendship(status.author.screen_name)
            except tweepy.error.TweepError as e:
                utils.logger.exception("I couldn't follow this user back.")

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

            akari = Akari(text, type='animation')
            text = akari.caption
            image = akari.filename
        except ImageSearchNoResultsException:
            utils.logger.exception('No results')
            msgs = ('No he encontrado nada...',
                    'No hay resultados.',
                    'No entiendo nada.',
                    'No sé lo que quieres.')
            text = random.choice(msgs)
            image = 'no-results.gif'
        except KeyboardInterrupt:
            raise
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
            twitter.post(status=reply, media=image,
                         in_reply_to_status_id=status.id)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            utils.logger.exception('Error posting.')

    def on_error(self, status_code):
        utils.logger.warning('An error has occured! Status code = {}'
                             .format(status_code))
        return True  # keep stream alive

    def on_timeout(self):
        print('Snoozing Zzzzzz')


if __name__ == '__main__':
    listener = TwitterBot()
    stream = tweepy.Stream(twitter.auth, listener)
    stream.userstream()
