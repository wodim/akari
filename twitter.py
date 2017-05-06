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
        except tweepy.error.TweepError as exc:
            Twitter.handle_exception(exc)
            raise

        utils.logger.info('Twitter API initialised.')

    def post(self, status='', media=None, retries=5, **kwargs):
        # this is a wrapper around _post() so it's retried several times
        # if there's a server-side exception.
        for _ in range(retries):
            try:
                self._post(status=status, media=media, **kwargs)
            except (tweepy.error.TweepError,
                    tweepy.error.RateLimitError) as exc:
                api_code, message = self.extract_exception(exc)
                if api_code in {130, 131}:  # over capacity, internal error
                    utils.logger.info('Server-side error. Retrying...')
                else:
                    raise
            else:
                return

    def _post(self, status, media, **kwargs):
        if not status and not media:
            raise ValueError('Nothing to post.')

        if media:
            status = utils.ellipsis(status, self.MAX_STATUS_WITH_MEDIA_LENGTH)
            utils.logger.info('Posting "%s" with "%s"', status, media)
            status = self.api.update_with_media(media, status=status, **kwargs)
        else:
            status = utils.ellipsis(status, self.MAX_STATUS_LENGTH)
            utils.logger.info('Posting "%s"', status)
            status = self.api.update_status(status, **kwargs)

        url = self.status_to_url(status)
        utils.logger.info('Status posted successfully: %s', url)

    @staticmethod
    def status_to_url(status):
        template = 'https://twitter.com/{user}/status/{id}'
        return template.format(id=status.id, user=status.user.screen_name)

    @staticmethod
    def extract_exception(exc):
        # revisit this when tweepy gets its shit together
        reason = json.loads(exc.reason.replace("'", '"'))[0]
        return reason['code'], reason['message']

    @staticmethod
    def handle_exception(exc):
        if not config.get('mail', 'enabled', type=bool):
            return

        api_code, message = Twitter.extract_exception(exc)
        user = 'e_%d' % api_code
        rate_limit = utils.ratelimit_hit('twitter_e', user, 1, 7200)
        if rate_limit['allowed']:
            title = 'Error %d connecting to Twitter' % api_code
            text = ('The following error has occurred when I tried to ' +
                    'connect to Twitter:\n\n' +
                    '%d: %s\n\n' % (api_code, message))
            utils.send_email(title, text)


twitter = Twitter(config.get('twitter', 'consumer_key'),
                  config.get('twitter', 'consumer_secret'),
                  config.get('twitter', 'access_token'),
                  config.get('twitter', 'access_token_secret'))
