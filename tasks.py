from datetime import datetime, timedelta

import tweepy

from config import cfg
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


def unfollow_spammers():
    for page in tweepy.Cursor(twitter.api.friends, count=200).pages():
        for user in page:
            if not is_eligible(user):
                utils.logger.info('Unfollowing @%s (%d)',
                                  user.screen_name, user.id)
                try:
                    twitter.api.destroy_friendship(user.id)
                except tweepy.error.TweepError:
                    utils.logger.exception('Error unfollowing.')


def is_eligible(user):
    """checks if a user is eligible to be followed."""
    if (cfg('tasks:follow_max_friends:int') and
            user.friends_count > cfg('tasks:follow_max_friends:int')):
        utils.logger.info('@%s has too many friends: %d', user.screen_name,
                          user.friends_count)
        return False
    if (cfg('tasks:follow_min_followers:int') and
            user.followers_count < cfg('tasks:follow_min_followers:int')):
        utils.logger.info('@%s has too few followers: %d', user.screen_name,
                          user.followers_count)
        return False
    if (cfg('tasks:follow_only_lang:list') and
            user.lang.lower() not in cfg('tasks:follow_only_lang:list')):
        utils.logger.info('@%s uses a language not in the whitelist: %s',
                          user.screen_name, user.lang.lower())
        return False
    if cfg('tasks:follow_last_post_days:int') and hasattr(user, 'status'):
        delta_min = (datetime.now() -
                     timedelta(days=cfg('tasks:follow_last_post_days:int')))
        if user.status.created_at < delta_min:
            utils.logger.info('@%s has not posted anything for too long',
                              user.screen_name)
            return False

    return True


def retweet_promo_tweet():
    promo_tweet_id = cfg('twitter:promo_tweet_id:int')
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
