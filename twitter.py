from tweepy import OAuthHandler
from tweepy import API

from config import config
import utils


class Twitter(object):
    MAX_STATUS_LENGTH = 140
    MAX_STATUS_WITH_MEDIA_LENGTH = 116

    def __init__(self,
                 consumer_key, consumer_secret,
                 access_token, access_token_secret):
        self.auth = OAuthHandler(consumer_key, consumer_secret)
        self.auth.set_access_token(access_token, access_token_secret)
        self.api = API(self.auth)
        self.me = self.api.me()

        utils.logger.info('Twitter API initialised.')

    def post(self, status='', media=None, truncate=True, **kwargs):
        if not status and not media:
            raise ValueError('Nothing to post.')

        if media:
            if truncate:
                status = utils.ellipsis(status,
                                        self.MAX_STATUS_WITH_MEDIA_LENGTH)
            utils.logger.info('Posting "{}" with "{}"'.format(status, media))
            self.api.update_with_media(media, status=status, **kwargs)
        else:
            if truncate:
                status = utils.ellipsis(status, self.MAX_STATUS_LENGTH)
            utils.logger.info('Posting "{}"'.format(status))
            self.api.update_status(status, **kwargs)


twitter = Twitter(config['twitter']['consumer_key'],
                  config['twitter']['consumer_secret'],
                  config['twitter']['access_token'],
                  config['twitter']['access_token_secret'])
