from tweepy import OAuthHandler
from tweepy import API

from config import config

auth = OAuthHandler(config['twitter']['consumer_key'],
                    config['twitter']['consumer_secret'])
auth.set_access_token(config['twitter']['access_token'],
                      config['twitter']['access_token_secret'])
api = API(auth)
