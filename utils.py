import functools
from html import unescape
import logging
import re
import threading

import redis
import requests

from config import config


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


class DB(object):
    server_available = False

    def __init__(self):
        self.server = redis.Redis(socket_connect_timeout=1)
        try:
            self.server.ping()
            logger.warning('Redis initialised.')
            self.server_available = True
        except Exception as e:
            logger.warning('Redis server unavailable: ' + str(e))

db = DB()


class RateLimit(object):
    # allowed: whether the action was accepted
    # left: how many requests are left until next reset
    # reset: how many seconds until the rate limit is reset
    def hit(self, prefix, user, max=50, ttl=60 * 10):
        def r(x, y, z): return {'allowed': x, 'left': y, 'reset': z}
        # if the server is not available, let it through
        if not db.server_available:
            return r(True, 1, 0)

        key = str(prefix) + ':' + str(user)
        value = db.server.get(key)

        if not value:
            # if key does not exist...
            db.server.set(key, 1)
            db.server.expire(key, ttl)
            return r(True, max - 1, ttl)
        else:
            current_ttl = db.server.ttl(key)
            if int(value) >= max:
                return r(False, 0, current_ttl)
            else:
                db.server.incr(key)
                return r(True, max - 1 - int(value), current_ttl)

rate_limit = RateLimit()


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


def build_path(hash_, kind):
    if kind == 'meta':
        ext = 'txt'
    elif kind == 'animation':
        ext = 'gif'
    else:
        ext = 'jpg'

    return 'images/image_{}_{}.{}'.format(hash_, kind, ext)


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
