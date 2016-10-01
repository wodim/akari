import random

import tweepy

from akari import Akari
from config import config
from followers import is_eligible
from image_search import ImageSearchNoResultsException
from translator import Translator, TranslatorException
from twitter import twitter
import utils


class StreamException(Exception):
    pass


class TwitterBot(tweepy.streaming.StreamListener):
    def on_status(self, status):
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
            utils.logger.info(('{id} - Ignoring because of low follower count'
                               .format(id=int(status.id))))
            return

        # check ratelimit
        rate_limit = utils.rate_limit.hit('twitter', 'global', 3, 5)
        if not rate_limit['allowed']:
            utils.logger.info(('{id} - Ignoring because of ratelimit'
                               .format(id=int(status.id))))
            return

        # so we'll generate something for this guy...
        # this is in a function of its own with a "new thread" decorator
        self.print_status(status)
        self.process(status, text)

    @utils.background
    def process(self, status, text):
        # follow the user if he's new. if he does not follow back, he'll
        # be unfollowed by followers.unfollow_my_unfollowers sometime later.
        if is_eligible(status.author):
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

            akari = Akari(text, type='animation', shuffle_results=True)
            text = akari.caption
            image = akari.filename
        except ImageSearchNoResultsException:
            utils.logger.exception('No results')
            msgs = ('I found nothing.',
                    'No results.',
                    "I don't understand...",
                    "I don't know what you mean by that.")
            text = random.choice(msgs)
            image = 'no-results.gif'
        except KeyboardInterrupt:
            raise
        except Exception as e:
            utils.logger.exception('Error composing the image')
            msgs = ("Can't hear ya...",
                    "Ooops, I'm a bit busy at the moment.",
                    "I don't feel so well right now.",
                    'Sorry, I fell asleep.')
            text = random.choice(msgs) + ' Try again a bit later.'
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

    def print_status(self, status):
        utils.logger.info('{id} - "{text}" by {screen_name} via {source}'
                          .format(id=status.id,
                                  text=utils.clean(status.text),
                                  screen_name=status.author.screen_name,
                                  source=status.source))

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
