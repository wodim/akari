import os
import random

import tweepy

from akari import Akari
from cache import cache
from config import cfg
from tasks import is_eligible
from image_search import ImageSearchNoResultsError
from twitter import twitter
import utils


class TwitterBot(tweepy.streaming.StreamListener):
    def __init__(self):
        super().__init__()
        self.lucky_interval = cfg('twitter:lucky_interval:int')
        if self.lucky_interval:
            self.lucky_interval *= 60
        self.sources_whitelist = cfg('twitter:sources_whitelist:list')
        self.user_requests = cfg('twitter:user_requests:bool')
        if self.user_requests is None:
            self.user_requests = True
        self.request_blacklist = cfg('twitter:request_blacklist:re_list')
        self.user_images = cfg('twitter:user_images:bool')
        if self.user_images is None:
            self.user_images = True
        self.delete_triggers = cfg('twitter:delete_triggers:re_list')
        self.load_avg_still = cfg('twitter:load_avg_still:int')
        self.no_results_image = cfg('twitter:no_results_image')
        self.error_image = cfg('twitter:error_image')

    def on_status(self, status):
        # ignore yourself
        if status.author.screen_name == twitter.me.screen_name:
            return

        # ignore retweets
        if hasattr(status, 'retweeted_status'):
            return

        # if the sources whitelist is enabled, ignore those who aren't on it
        if (self.sources_whitelist and
                status.source not in self.sources_whitelist):
            return

        text = utils.clean(status.text, urls=True, replies=True, rts=True)

        # if you are not talking to me, or if requests are disabled...
        if (not status.text.startswith('@' + twitter.me.screen_name) or
                not self.user_requests):
            if text:
                text_no_nl = utils.clean(status.text)
                # store this status to score it later in akari_cron
                with open('pending.txt', 'a') as p_file:
                    print('%d %s' % (status.id, text_no_nl), file=p_file)

                # generate an unsolicited image for someone every once in
                # a while.
                if self._got_lucky():
                    self._print_status(status)
                    utils.logger.warning('%d - Lucky of the draw!', status.id)
                    self._process(status, text, suppress_errors=True)

            # then return
            return

        # see if the text in this request is blacklisted. if so do nothing.
        if (self.request_blacklist and
                any(x.search(text) for x in self.request_blacklist)):
            return

        # see if there's an image (and if that's allowed)
        image_url = None
        try:
            if self.user_images:
                image_url = status.entities['media'][0]['media_url'] + ':orig'
        except KeyError:
            pass

        # if there's a user-provided image but there's no text and we are
        # generating still images, don't do anything at all (in this case,
        # we would just copy the image around without doing anything useful)
        if image_url and not text and len(cache.get('akari:frames')) < 2:
            return

        # if after being cleaned up the status turns out to be empty and
        # there's no image, return
        if not text and not image_url:
            return

        self._print_status(status)

        try:
            if (self.delete_triggers and
                    any(x.search(text) for x in self.delete_triggers)):
                if self._self_delete(status):
                    return
            # if removal is not successful, we will generate a caption.
        except KeyError:
            pass

        # apply a strict ratelimit to people with fewer than 25 followers
        rate_limit_slow = utils.ratelimit_hit('twitter', 'global_slow', 5, 60)
        if (status.author.followers_count < 25 and
                not rate_limit_slow['allowed']):
            utils.logger.info('%d - Ignoring because of low follower count',
                              status.id)
            return

        # apply a lax ratelimit to the rest of users
        rate_limit = utils.ratelimit_hit('twitter', 'global', 20, 60)
        if not rate_limit['allowed']:
            utils.logger.info('%d - Ignoring because of ratelimit', status.id)
            return

        # so we'll generate something for this guy...
        # this is in a function of its own with a "new thread" decorator
        self._process(status, text, image_url)

    @utils.background
    def _process(self, status, text, image_url=None, suppress_errors=False):
        # follow the user if he's new. if he does not follow back, he'll
        # be unfollowed by followers.unfollow_my_unfollowers sometime later.
        if is_eligible(status.author):
            try:
                twitter.api.create_friendship(status.author.screen_name)
            except tweepy.error.TweepError:
                pass

        # if the one-minute load avg is greater than load_avg_still, generate
        # still captions
        try:
            load_avg = os.getloadavg()[0]
            if self.load_avg_still and load_avg > self.load_avg_still:
                utils.logger.warning('Load average too high! (%i > %i)',
                                     load_avg, self.load_avg_still)
                akari_type = 'still'
            else:
                akari_type = 'animation'
        except KeyError:
            pass

        error = False
        try:
            akari = Akari(text, type=akari_type, shuffle_results=True,
                          image_url=image_url)
            text = akari.caption
            image = akari.filename
        except ImageSearchNoResultsError:
            if suppress_errors:
                return
            utils.logger.exception('No results')
            msgs = ('I found nothing.',
                    'No results.',
                    "I didn't find anything.",
                    'There are no results.')
            text = random.choice(msgs)
            image = self.no_results_image
            error = True
        except KeyboardInterrupt:
            raise
        except Exception:
            if suppress_errors:
                return
            utils.logger.exception('Error composing the image')
            msgs = ("Can't hear ya...",
                    "Ooops, I'm busy at the moment.",
                    "I don't feel so well right now.",
                    'Sorry, I fell asleep.')
            text = '%s Try again a bit later.' % random.choice(msgs)
            image = self.error_image
            error = True

        # start building a reply. prepend @nick of whoever we are replying to
        if cfg('twitter:text_in_status:bool') or error:
            reply = '@%s %s' % (status.author.screen_name, text)
        else:
            reply = '@%s' % (status.author.screen_name)

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

    @utils.background
    def _self_delete(self, status):
        if not status.in_reply_to_status_id:
            utils.logger.warning('This status has no "in reply to" field.')
            return False

        try:
            status_del = twitter.api.get_status(status.in_reply_to_status_id)
        except tweepy.error.TweepError:
            utils.logger.exception('Failed to get the status pointed by '
                                   'the "in reply to" field.')
            return False

        if not status_del.text.startswith('@%s ' % status.user.screen_name):
            utils.logger.warning('The status pointed by the "in reply to" '
                                 "wasn't in reply to a status made by the "
                                 'user who requested the removal.')
            return False

        try:
            twitter.api.destroy_status(status_del.id)
        except tweepy.error.TweepError:
            utils.logger.exception('Failed to remove the status pointed by '
                                   'the "in reply to" field.')
            return False
        else:
            utils.logger.info('Deleted: %d "%s"', status_del.id,
                              status_del.text)
            return True

    def _print_status(self, status):
        utils.logger.info('%d - "%s" by %s via %s',
                          status.id, utils.clean(status.text),
                          status.author.screen_name, status.source)

    def _got_lucky(self):
        if not self.lucky_interval:
            return False

        rl_lucky = utils.ratelimit_hit('twitter', 'lucky', 1,
                                       self.lucky_interval)
        if rl_lucky['allowed']:
            return True

        return False

    def on_error(self, status_code):
        utils.logger.warning('An error has occured! Status code = %d',
                             status_code)
        return True  # keep stream alive

    def on_timeout(self):
        print('Snoozing Zzzzzz')


if __name__ == '__main__':
    Akari.warmup()

    listener = TwitterBot()
    stream = tweepy.Stream(twitter.auth, listener)
    stream.userstream()
