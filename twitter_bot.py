import random

import tweepy

from akari import Akari
from config import config
from tasks import is_eligible
from image_search import ImageSearchNoResultsError
from twitter import twitter
import utils


class TwitterBot(tweepy.streaming.StreamListener):
    def on_status(self, status):
        # ignore yourself
        if status.author.screen_name == twitter.me.screen_name:
            return

        # ignore retweets
        if hasattr(status, 'retweeted_status'):
            return

        # if the sources whitelist is enabled, ignore those who aren't on it
        whitelist = config.get('twitter', 'sources_whitelist', type=list)
        if whitelist and status.source not in whitelist:
            return

        text = utils.clean(status.text, urls=True, replies=True, rts=True)

        # if after being cleaned the status turns out to be empty, return
        if text == '':
            return

        # if you are not talking to me...
        if not status.text.startswith('@' + twitter.me.screen_name):
            # store this status to score it later in akari_cron
            with open('pending.txt', 'a') as p_file:
                print('%d %s' % (status.id, text), file=p_file)

            # then return
            return

        # apply a strict ratelimit to people with fewer than 25 followers
        rate_limit_slow = utils.ratelimit_hit('twitter', 'global_slow', 5, 60)
        if (status.author.followers_count < 25 and
                not rate_limit_slow['allowed']):
            utils.logger.info('%d - Ignoring because of low follower count',
                              status.id)
            return

        # apply a lax ratelimit to the rest of users
        rate_limit = utils.ratelimit_hit('twitter', 'global', 3, 5)
        if not rate_limit['allowed']:
            utils.logger.info('%d - Ignoring because of ratelimit', status.id)
            return

        # so we'll generate something for this guy...
        # this is in a function of its own with a "new thread" decorator
        self._print_status(status)
        self._process(status, text)

    @utils.background
    def _process(self, status, text):
        # follow the user if he's new. if he does not follow back, he'll
        # be unfollowed by followers.unfollow_my_unfollowers sometime later.
        if is_eligible(status.author):
            try:
                twitter.api.create_friendship(status.author.screen_name)
            except tweepy.error.TweepError:
                pass

        try:
            akari = Akari(text, type='animation', shuffle_results=True)
            text = akari.caption
            image = akari.filename
        except ImageSearchNoResultsError:
            utils.logger.exception('No results')
            msgs = ('I found nothing.',
                    'No results.',
                    "I didn't find anything.",
                    'There are no results.')
            text = random.choice(msgs)
            image = config.get('twitter', 'no_results_image')
        except KeyboardInterrupt:
            raise
        except Exception:
            utils.logger.exception('Error composing the image')
            msgs = ("Can't hear ya...",
                    "Ooops, I'm a bit busy at the moment.",
                    "I don't feel so well right now.",
                    'Sorry, I fell asleep.')
            text = random.choice(msgs) + ' Try again a bit later.'
            image = config.get('twitter', 'error_image')

        # start building a reply. prepend @nick of whoever we are replying to
        reply = '@%s %s' % (status.author.screen_name, text)

        # post it
        try:
            twitter.post(status=reply, media=image,
                         in_reply_to_status_id=status.id)
        except KeyboardInterrupt:
            raise
        except tweepy.error.TweepError as exc:
            utils.logger.exception('Error posting.')
            if exc.api_code == 326:  # account temporarily locked
                twitter.handle_exception(exc)
        except Exception:
            utils.logger.exception('Error posting.')

    def _print_status(self, status):
        utils.logger.info('%d - "%s" by %s via %s',
                          status.id, utils.clean(status.text),
                          status.author.screen_name, status.source)

    def on_error(self, status_code):
        utils.logger.warning('An error has occured! Status code = %d',
                             status_code)
        return True  # keep stream alive

    def on_timeout(self):
        print('Snoozing Zzzzzz')


if __name__ == '__main__':
    listener = TwitterBot()
    stream = tweepy.Stream(twitter.auth, listener)
    stream.userstream()
