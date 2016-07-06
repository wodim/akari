import tweepy

from twitter import twitter


def follow_my_followers():
    for user in tweepy.Cursor(twitter.api.followers).items(100):
        if not user.following:
            user.follow()
