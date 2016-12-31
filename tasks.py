import tweepy

from config import config
from twitter import twitter
import utils


def follow_my_followers():
    for page in tweepy.Cursor(twitter.api.followers, count=200).pages():
        for user in page:
            if (not user.following and
                    not user.follow_request_sent and
                    is_eligible(user)):
                utils.logger.info('Following @%s (%d) back',
                                  user.screen_name, user.id)
                try:
                    user.follow()
                except tweepy.error.TweepError as exc:
                    utils.logger.exception('Error following.')
                    if exc.api_code == 161:
                        # "you are unable to follow more people at this time"
                        # don't keep trying because it will just not work.
                        msg = "Can't follow anyone else. Giving up."
                        utils.logger.info(msg)
                        return


def unfollow_my_unfollowers():
    # 100 per page is the max lookup_friendships can do
    for page in tweepy.Cursor(twitter.api.friends, count=100).pages():
        user_ids = [user.id for user in page]
        for relationship in twitter.api._lookup_friendships(user_ids):
            if not relationship.is_followed_by:
                utils.logger.info('Unfollowing @%s (%d)',
                                  relationship.screen_name, relationship.id)
                try:
                    twitter.api.destroy_friendship(relationship.id)
                except tweepy.error.TweepError:
                    utils.logger.exception('Error unfollowing.')


def is_eligible(user):
    """checks if a user is eligible to be followed."""
    if user.friends_count > 5000:
        return False
    if (user.followers_count > 5000 and
            user.friends_count / user.followers_count > 0.7):
        return False

    return True


def retweet_promo_tweet():
    promo_tweet_id = config.get('twitter', 'promo_tweet_id', type=int)
    try:
        tweet = twitter.api.get_status(promo_tweet_id, include_my_retweet=True)
    except tweepy.error.TweepError:
        utils.logger.error('Error retrieving info about the promo tweet.')
        raise

    try:
        current_rt_id = tweet.current_user_retweet['id']
        utils.logger.info('Undoing previous retweet of the promo tweet.')
        twitter.api.destroy_status(current_rt_id)
    except AttributeError:
        # this happens when there was no retweet to undo
        pass
    except tweepy.error.TweepError:
        utils.logger.error('Error undoing the retweet.')
        raise  # if there was an error undoing the retweet, give up

    try:
        twitter.api.retweet(promo_tweet_id)
    except tweepy.error.TweepError:
        utils.logger.error('Error retweeting the promo tweet.')
        raise

    utils.logger.info('Promo tweet retweeted.')
