import functools
import hashlib
import html
import logging
import pickle
import re
import textwrap
import threading

import requests

from config import cfg


class Logger(object):
    def __init__(self):
        for logger in ('requests', 'urllib3', 'tweepy'):
            logging.getLogger(logger).setLevel(logging.WARNING)

        format_ = ('{asctime}: {process:>5} '
                   '[{filename:>16}:{lineno:<4} {funcName:>16}()] {message}')
        logging.basicConfig(format=format_, style='{',
                            datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)
        self.logger = logging.getLogger('akari_endlosung')

    def get_logger(self):
        return self.logger


logger = Logger().get_logger()


class DB(object):
    """wrapper for redis"""
    server_available = False

    def __init__(self):
        try:
            import redis
            self.server = redis.Redis(socket_connect_timeout=1)
            self.server.ping()
            self.server_available = True
        except ImportError as exc:
            logger.warning('Redis library could not be imported: %s', exc)
        except Exception as exc:
            logger.warning('Redis server unavailable: %s', exc)


db = DB()


def ratelimit_hit(prefix, user, max_=50, ttl=60 * 10):
    """Hits a ratelimit.
        In:
            prefix: prefix of the ratelimit (twitter, etc)
            user:   postfix of the ratelimit (a specific user, general, etc)
            max_:   max number of hits allowed in ttl secs
            ttl:    secs until the ratelimit is reset (default: 10 mins)
        Out:
            allowed: whether the hit was allowed
            left:    hits left until next reset
            reset:   seconds left until next reset
    """
    def r(x, y, z):
        return {'allowed': x, 'left': y, 'reset': z}
    # if the server is not available, let it through
    if not db.server_available:
        return r(True, 1, 0)

    key = '%s:%s' % (prefix, user)
    value = db.server.get(key)
    if not value:
        # if key does not exist...
        db.server.set(key, 1)
        db.server.expire(key, ttl)
        return r(True, max_ - 1, ttl)
    else:
        current_ttl = db.server.ttl(key)
        if not current_ttl:
            # for some reason sometimes redis stores the keys with no ttl.
            # this means the ratelimit is never reset and the bot stays locked.
            # if that happens just remove the key and accept the hit.
            db.server.delete(key)
            return r(True, max_ - 1, ttl)
        if int(value) >= max_:
            return r(False, 0, current_ttl)
        else:
            db.server.incr(key)
            return r(True, max_ - 1 - int(value), current_ttl)


def timedelta(time_):
    elapsed = time_

    if not time_:
        return 'a moment'
    elif time_ > 3600:
        elapsed //= 3600
        if elapsed == 1:
            return 'one hour'
        else:
            return '%d hours' % elapsed
    elif time_ > 60:
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
    """cleans up text that comes from twitter."""
    text = text.replace('\n', ' ')
    text = text.replace('\r', ' ')
    text = html.unescape(text)
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
    return textwrap.shorten(text, width=max_length, placeholder='…')


def decay(time_, max_time, coeff):
    """returns a multiplier that starts at coeff + 1.0 and linearly approaches
        1.0 as time_ approaches max_time"""
    threshold = max_time - time_
    if threshold < 0:
        threshold = 0
    return 1 + threshold * coeff / max_time


def background(func):
    """executes the function in a thread of its own"""
    @functools.wraps(func)
    def background_func(*args, **kwargs):
        thread = threading.Thread(target=func, args=args, kwargs=kwargs)
        thread.start()
        return thread
    return background_func


def send_email(subject, text):
    """sends an email using the mailgun http api"""
    url = ('https://api.mailgun.net/v3/%s/messages' %
           cfg('mail:mailgun_domain'))
    auth = ('api', cfg('mail:mailgun_key'))
    data = {'from': 'Akari Bot <%s>' % cfg('mail:from'),
            'to': [cfg('mail:to')],
            'subject': subject, 'text': text}
    return requests.post(url, auth=auth, data=data)


# from reddit
def _make_hashable(s):
    if isinstance(s, str):
        return s
    elif isinstance(s, (tuple, list)):
        return ','.join(_make_hashable(x) for x in s)
    elif isinstance(s, dict):
        return ','.join('%s:%s' % (_make_hashable(k), _make_hashable(v))
                        for (k, v) in sorted(s.items()))
    else:
        return s


# from reddit
def make_key_id(*args, **kwargs):
    h = hashlib.md5()
    h.update(_make_hashable(args).encode('utf-8'))
    h.update(_make_hashable(kwargs).encode('utf-8'))
    return h.hexdigest()


def memoize(name, timeout=30):
    def memoize_fn(func):
        @functools.wraps(func)
        def new_fn(*args, **kwargs):
            if not db.server_available:
                # if redis is unavailable just do your job and return.
                return func(*args, **kwargs)

            key = 'memo:%s:%s' % (name, make_key_id(*args, **kwargs))

            res = db.server.get(key)

            if res:
                try:
                    res = pickle.loads(res)
                    logger.info('Returning object from cache: %s for "%s/%s"',
                                key, _make_hashable(args),
                                _make_hashable(kwargs))
                except TypeError:
                    # this key got fucked up. remove it and pretend we didn't
                    # see it
                    db.server.delete(key)
                    res = None
                    logger.warning('Destroying corrupt object in cache: %s',
                                   key)

            if not res:
                # not cached, we should calculate it.
                res = func(*args, **kwargs)
                db.server.set(key, pickle.dumps(res))
                # ttl is set here so it cannot be overridden
                db.server.expire(key, timeout)

            return res
        return new_fn
    return memoize_fn
