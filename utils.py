import functools
from html import unescape
import logging
import re
import threading
import time

import requests

from config import config, Config


class Logger(object):
    def __init__(self):
        for i in ('requests', 'urllib3', 'tweepy'):
            logging.getLogger(i).setLevel(logging.WARNING)

        format = ('[{filename:>16}:{lineno:<4} {funcName:>16}()] ' +
                  '{asctime}: {message}')
        logging.basicConfig(format=format,
                            style='{',
                            datefmt='%Y-%m-%d %H:%M:%S',
                            level=logging.INFO)
        self.logger = logging.getLogger('akari_endlosung')
        self.logger.info('Logger initialised.')

    def get_logger(self):
        return self.logger

logger = Logger().get_logger()


# allowed: whether the action was accepted
# left: how many requests are left until next reset
# reset: how many seconds until the rate limit is reset
def ratelimit_hit(prefix, user, max=50, ttl=60 * 10):
    def r(x, y, z, unavailable=True):
        return dict(allowed=x, left=y, reset=z, unavailable=unavailable)

    key = str(prefix) + ':' + str(user)
    current_ts = int(time.time())

    try:
        with Config('rate_limits.ini', cached_reads=False) as rl:
            try:
                count = rl.get(key, 'count', int)
                ts = rl.get(key, 'ts', int)
                if ts + ttl > current_ts:  # this rl is still in effect
                    left = ts + ttl - current_ts
                    if count >= max:  # don't allow this request
                        return r(False, 0, left)
                    else:  # allow this request and sum it
                        rl.set(key, 'count', count + 1)
                        return r(True, max - count + 1, left)
                else:  # this rl has expired already, renew it
                    rl.set(key, 'count', 1)
                    rl.set(key, 'ts', current_ts)
                    return r(True, max - 1, ttl)
            except KeyError:
                # new rl
                rl.set(key, 'count', 1)
                rl.set(key, 'ts', current_ts)
                return r(True, max - 1, ttl)
    except OSError:
        # file is locked or something, so just allow it
        logger.exception("Couldn't open ratelimit file!")
        return r(True, 1, 0, unavailable=True)


def timedelta(time):
    elapsed = time

    if not time:
        return 'a moment'
    elif time > 3600:
        elapsed //= 3600
        if elapsed == 1:
            return 'one hour'
        else:
            return '%d hours' % elapsed
    elif time > 60:
        elapsed //= 60
        if elapsed == 1:
            return 'one minute'
        else:
            return '%d minutes' % elapsed
    else:
        if elapsed == 1:
            return 'one second'
        else:
            return '%d seconds' % elapsed


regex_rts = re.compile(r'^RT @[a-zA-Z0-9_]+:\s')
regex_replies = re.compile(r'@[a-zA-Z0-9_]+\s?')
regex_hashtags = re.compile(r'#[a-zA-Z0-9_]+\s?')
regex_urls = re.compile(r'https?://[\w\./]*\b')
regex_whitespace = re.compile(r'\s+')
def clean(text, replies=False, hashtags=False, rts=False, urls=False):
    text = text.replace('\n', ' ')
    text = text.replace('\r', ' ')
    text = unescape(text)

    if rts:
        text = regex_rts.sub('', text)

    if replies:
        text = regex_replies.sub('', text)

    if hashtags:
        text = regex_hashtags.sub('', text)

    if urls:
        text = regex_urls.sub('', text)

    text = regex_whitespace.sub(' ', text)
    text = text.strip()

    return text


def ellipsis(text, max_length):
    if len(text) > max_length:
        return text[:max_length - 1] + '…'
    else:
        return text


def decay(time, max_time, coeff):
    threshold = max_time - time
    if threshold < 0:
        threshold = 0
    return 1 + threshold * (coeff - 1) / max_time


def background(func):
    @functools.wraps(func)
    def background_func(*args, **kwargs):
        thread = threading.Thread(target=func, args=args, kwargs=kwargs)
        thread.start()
        return thread

    return background_func


def send_email(subject, text):
    """sends an email using the mailgun http api"""
    url = ('https://api.mailgun.net/v3/%s/messages' %
           config.get('mail', 'mailgun_domain'))
    auth = ('api', config.get('mail', 'mailgun_key'))
    data = {'from': 'Akari Bot <%s>' % config.get('mail', 'from'),
            'to': [config.get('mail', 'to')],
            'subject': subject, 'text': text}
    return requests.post(url, auth=auth, data=data)
