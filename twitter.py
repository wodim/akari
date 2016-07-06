from tweepy import OAuthHandler
from tweepy import API

from config import config
from utils import logger


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

        logger.info('Twitter API initialised.')

twitter = Twitter(config['twitter']['consumer_key'],
                  config['twitter']['consumer_secret'],
                  config['twitter']['access_token'],
                  config['twitter']['access_token_secret'])
