import os
import random

import tweepy

from akari import Akari
from cache import cache
from config import cfg, cfgs, Config
from parallel import Parallel
from tasks import is_eligible
from image_search import ImageSearchNoResultsError
from twitter import twitter
import utils


state_config = Config('state.ini')


def process_timeline():
    """retrieves all tweets in the home timeline and then stores them in
        pending.txt"""
    params = dict(count=200)
    sources_whitelist = cfg('twitter:sources_whitelist:list')

    try:
        since_id = cfg('last_ids:home_timeline:int',
                       config_handle=state_config)
        if since_id:
            utils.logging.info('State: since_id=%d', since_id)
            params['since_id'] = since_id
        else:
            utils.logging.warning("There's no last id saved, "
                                  "so I'm starting from the beginning.")
    except Exception as exc:
        utils.logging.exception("Couldn't figure what the last tweet was, "
                                "so I'm starting from the beginning.")

    filtered_statuses = []
    statuses = [status for page in
                tweepy.Cursor(twitter.api.home_timeline, **params).pages()
                for status in page]
    # they are in reverse chronological order, so put them straight
    statuses = statuses[::-1]
    for status in statuses:
        # ignore yourself
        if status.author.screen_name == twitter.me.screen_name:
            continue

        # ignore mentions
        if status.text.startswith('@'):
            continue

        # ignore retweets
        if hasattr(status, 'retweeted_status'):
            continue

        # if the sources whitelist is enabled, ignore those who aren't on it
        if (sources_whitelist and status.source not in sources_whitelist):
            continue

        text = utils.clean(status.text, urls=True, replies=True, rts=True)
        if not text:
            continue

        # store this status to score it later in akari_cron
        filtered_statuses.append(status)

    if filtered_statuses:
        with open('pending.txt', 'a') as p_file:
            for status in filtered_statuses:
                text_no_nl = utils.clean(status.text)
                print('%d %s' % (status.id, text_no_nl), file=p_file)
        utils.logging.info('Retrieved %d new statuses (from %d to %d).',
                           len(filtered_statuses), filtered_statuses[0].id,
                           filtered_statuses[-1].id)
        cfgs('last_ids:home_timeline', str(filtered_statuses[-1].id),
             config_handle=state_config)
    else:
        utils.logging.info('Retrieved no new statuses.')


def process_mentions():
    """retrieves all mentions and generates captions for those who are fighting
        fit"""
    if not cfg('twitter:user_requests:bool'):
        return

    params = dict(count=200)
    sources_whitelist = cfg('twitter:sources_whitelist:list')
    mention_prefix = '@%s ' % twitter.me.screen_name.lower()

    since_id = cfg('last_ids:mentions_timeline:int',
                   config_handle=state_config)
    if since_id:
        utils.logging.info('State: since_id=%d', since_id)
        params['since_id'] = since_id
    else:
        utils.logging.warning("There's no last id saved, so I will save the "
                              'last id I see and then quit.')

    filtered_statuses = []
    statuses = [status for page in
                tweepy.Cursor(twitter.api.mentions_timeline, **params).pages()
                for status in page]
    # they are in reverse chronological order, so put them straight
    statuses = statuses[::-1]
    if not since_id:
        since_id = statuses[-1].id
        cfgs('last_ids:mentions_timeline', str(since_id),
             config_handle=state_config)
        utils.logging.info('New since_id=%d. Goodbye!', since_id)
        return

    for status in statuses:
        # ignore mentions that are not directed at me
        if not status.text.lower().startswith(mention_prefix):
            continue

        # ignore retweets
        if hasattr(status, 'retweeted_status'):
            continue

        # if the sources whitelist is enabled, ignore those who aren't on it
        if (sources_whitelist and status.source not in sources_whitelist):
            continue

        text = utils.clean(status.text, urls=True, replies=True, rts=True)
        if not text:
            continue

        # store this status
        filtered_statuses.append(status)

    if filtered_statuses:
        utils.logging.info('Retrieved %d new notifications (from %d to %d).',
                           len(filtered_statuses), filtered_statuses[0].id,
                           filtered_statuses[-1].id)
        cfgs('last_ids:mentions_timeline', str(filtered_statuses[-1].id),
             config_handle=state_config)

        Akari.warmup()

        parallel = Parallel(process_request, filtered_statuses,
                            cfg('twitter:process_threads:int') or 3)
        parallel.start()
    else:
        utils.logging.info('Retrieved no new notifications.')


def process_request(queue):
    request_blacklist = cfg('twitter:request_blacklist:re_list')
    user_images = cfg('twitter:user_images:bool')
    delete_triggers = cfg('twitter:delete_triggers:re_list')
    load_avg_still = cfg('twitter:load_avg_still:int')
    no_results_image = cfg('twitter:no_results_image')
    error_image = cfg('twitter:error_image')

    while True:
        status = queue.get()

        text = utils.clean(status.text, urls=True, replies=True, rts=True)

        # see if the text in this request is blacklisted. if so do nothing.
        if (request_blacklist and
                any(x.search(text) for x in request_blacklist)):
            print_status(status)
            utils.logger.warning('Text is blacklisted, request ignored')
            continue

        # see if there's an image (and if that's allowed)
        image_url = None
        try:
            if user_images:
                image_url = status.entities['media'][0]['media_url'] + ':orig'
        except KeyError:
            pass

        # if there's a user-provided image but there's no text and we are
        # generating still images, don't do anything at all (in this case,
        # we would just copy the image around without doing anything useful)
        if image_url and not text and len(cache.get('akari:frames')) < 2:
            return

        # if after being cleaned up the status turns out to be empty and
        # there's no image, return
        if not text and not image_url:
            return

        print_status(status)

        if (delete_triggers and any(x.search(text) for x in delete_triggers)):
            if process_self_delete(status):
                return
        # if removal is not successful, we will generate a caption.

        # apply a strict ratelimit to people with fewer than 25 followers
        rate_limit_slow = utils.ratelimit_hit('twitter', 'global_slow', 5, 60)
        if (status.author.followers_count < 25 and
                not rate_limit_slow['allowed']):
            utils.logger.info('%d - Ignoring because of low follower count',
                              status.id)
            return

        # apply a lax ratelimit to the rest of users
        rate_limit = utils.ratelimit_hit('twitter', 'global', 20, 60)
        if not rate_limit['allowed']:
            utils.logger.info('%d - Ignoring because of ratelimit', status.id)
            return

        # so we'll generate something for this guy...

        # follow the user if he's new. if he does not follow back, he'll
        # be unfollowed by followers.unfollow_my_unfollowers sometime later.
        if is_eligible(status.author):
            try:
                twitter.api.create_friendship(status.author.screen_name)
            except tweepy.error.TweepError:
                pass

        # if the one-minute load avg is greater than load_avg_still, generate
        # still captions
        try:
            load_avg = os.getloadavg()[0]
            if load_avg_still and load_avg > load_avg_still:
                utils.logger.warning('Load average too high! (%i > %i)',
                                     load_avg, load_avg_still)
                akari_type = 'still'
            else:
                akari_type = 'animation'
        except KeyError:
            pass

        error = False
        try:
            akari = Akari(text, type=akari_type, shuffle_results=True,
                          image_url=image_url)
            text = akari.caption
            image = akari.filename
        except ImageSearchNoResultsError:
            utils.logger.exception('No results')
            msgs = ('I found nothing.',
                    'No results.',
                    "I didn't find anything.",
                    'There are no results.')
            text = random.choice(msgs)
            image = no_results_image
            error = True
        except KeyboardInterrupt:
            raise
        except Exception:
            utils.logger.exception('Error composing the image')
            msgs = ("Can't hear ya...",
                    "Ooops, I'm busy at the moment.",
                    "I don't feel so well right now.",
                    'Sorry, I fell asleep.')
            text = '%s Try again a bit later.' % random.choice(msgs)
            image = error_image
            error = True

        # start building a reply. prepend @nick of whoever we are replying to
        if cfg('twitter:text_in_status:bool') or error:
            reply = '@%s %s' % (status.author.screen_name, text)
        else:
            reply = '@%s' % (status.author.screen_name)

        # post it
        try:
            twitter.post(status=reply, media=image,
                         in_reply_to_status_id=status.id)
        except KeyboardInterrupt:
            raise
        except tweepy.error.TweepError as exc:
            utils.logger.exception('Error posting.')
            if exc.api_code == 326:  # account temporarily locked
                twitter.handle_exception(exc)
        except Exception:
            utils.logger.exception('Error posting.')

        queue.task_done()


def process_self_delete(status):
    if not status.in_reply_to_status_id:
        utils.logger.warning('This status has no "in reply to" field.')
        return False

    try:
        status_del = twitter.api.get_status(status.in_reply_to_status_id)
    except tweepy.error.TweepError:
        utils.logger.exception('Failed to get the status pointed by '
                               'the "in reply to" field.')
        return False

    if not status_del.text.startswith('@%s ' % status.user.screen_name):
        utils.logger.warning('The status pointed by the "in reply to" '
                             "wasn't in reply to a status made by the "
                             'user who requested the removal.')
        return False

    try:
        twitter.api.destroy_status(status_del.id)
    except tweepy.error.TweepError:
        utils.logger.exception('Failed to remove the status pointed by '
                               'the "in reply to" field.')
        return False
    else:
        utils.logger.info('Deleted: %d "%s"', status_del.id,
                          status_del.text)
        return True


def print_status(status):
    utils.logger.info('%d - "%s" by %s via %s',
                      status.id, utils.clean(status.text),
                      status.author.screen_name, status.source)
