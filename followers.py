import random

import tweepy

from twitter import api


def follow_my_followers():
    for user in tweepy.Cursor(api.followers).items(100):
        if not user.following:
            user.follow()
