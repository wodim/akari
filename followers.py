import tweepy

from twitter import twitter


def follow_my_followers():
    for page in tweepy.Cursor(twitter.api.followers, count=200).pages():
        for user in page:
            if not user.following:
                user.follow()


def unfollow_my_unfollowers():
    # 100 per page is the max lookup_friendships can do
    for page in tweepy.Cursor(twitter.api.friends, count=100).pages():
        user_ids = [user.id for user in page]
        for user in twitter.api._lookup_friendships(user_ids):
            if not user.is_followed_by:
                twitter.api.destroy_friendship(user.id)
