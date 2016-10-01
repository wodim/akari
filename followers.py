import tweepy

from twitter import twitter
import utils


def follow_my_followers():
    for page in tweepy.Cursor(twitter.api.followers, count=200).pages():
        for user in page:
            if (not user.following and
                    not user.follow_request_sent and
                    is_eligible(user)):
                utils.logger.info('Following @{screen_name} ({id}) back'
                                  .format(screen_name=user.screen_name,
                                          id=user.id))
                try:
                    user.follow()
                except tweepy.error.TweepError as e:
                    utils.logger.exception('Error following.')


def unfollow_my_unfollowers():
    # 100 per page is the max lookup_friendships can do
    for page in tweepy.Cursor(twitter.api.friends, count=100).pages():
        user_ids = [user.id for user in page]
        for relationship in twitter.api._lookup_friendships(user_ids):
            if not relationship.is_followed_by:
                utils.logger.info('Unfollowing @{screen_name} ({id})'
                                  .format(screen_name=relationship.screen_name,
                                          id=relationship.id))
                try:
                    twitter.api.destroy_friendship(relationship.id)
                except tweepy.error.TweepError as e:
                    utils.logger.exception('Error unfollowing.')


def is_eligible(user):
    """checks if a user is eligible to be followed."""
    if user.friends_count > 5000:
        return False
    if (user.followers_count > 5000 and
            user.friends_count / user.followers_count > 0.7):
        return False

    return True
