import json

import tweepy

from config import config
import utils


class Twitter(object):
    MAX_STATUS_LENGTH = 140
    MAX_STATUS_WITH_MEDIA_LENGTH = 116

    def __init__(self,
                 consumer_key, consumer_secret,
                 access_token, access_token_secret):
        # all of this is encased in a try block to handle the case where this
        # account is either locked or suspended
        try:
            self.auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
            self.auth.set_access_token(access_token, access_token_secret)
            self.api = tweepy.API(self.auth)
            self.me = self.api.me()
        except tweepy.error.TweepError as e:
            self.handle_exception(e)
            raise

        utils.logger.info('Twitter API initialised.')

    def post(self, status='', media=None, **kwargs):
        if not status and not media:
            raise ValueError('Nothing to post.')

        if media:
            status = utils.ellipsis(status, self.MAX_STATUS_WITH_MEDIA_LENGTH)
            utils.logger.info('Posting "{}" with "{}"'.format(status, media))
            self.api.update_with_media(media, status=status, **kwargs)
        else:
            status = utils.ellipsis(status, self.MAX_STATUS_LENGTH)
            utils.logger.info('Posting "{}"'.format(status))
            self.api.update_status(status, **kwargs)

        utils.logger.info('Status posted successfully!')

    def extract_exception(self, e):
        # revisit this when tweepy gets its shit together
        reason = json.loads(e.reason.replace("'", '"'))[0]
        return reason['code'], reason['message']

    def handle_exception(self, e):
        if not config.get('mail', 'enabled', type=bool):
            return

        api_code, message = self.extract_exception(e)
        user = 'e_%d' % api_code
        rate_limit = utils.ratelimit_hit('twitter_e', user, 1, 7200)
        if not rate_limit['unavailable'] and rate_limit['allowed']:
            title = 'Error %d connecting to Twitter' % api_code
            text = ('The following error has occurred when I tried to ' +
                    'connect to Twitter:\n\n' +
                    '%d: %s\n\n' % (api_code, message))
            utils.send_email(title, text)


twitter = Twitter(config.get('twitter', 'consumer_key'),
                  config.get('twitter', 'consumer_secret'),
                  config.get('twitter', 'access_token'),
                  config.get('twitter', 'access_token_secret'))
