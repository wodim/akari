from html import unescape
import logging
import re

import redis


class Logger(object):
    def __init__(self):
        logging.basicConfig(format='%(asctime)s: %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S',
                            level=logging.INFO)
        self.logger = logging.getLogger('akari_endlosung')
        self.logger.info('Logger initialised.')

    def get_logger(self):
        return self.logger

logger = Logger().get_logger()


class DB(object):
    def __init__(self):
        self.server = redis.Redis(socket_connect_timeout=1)
        try:
            self.server.ping()
            logger.warning('Redis initialised.')
            self.server_available = True
        except Exception as e:
            logger.warning('Redis server unavailable: ' + str(e))
            self.server_available = False

db = DB()


class RateLimit(object):
    # returns a tuple: whether the action was accepted, how many requests are
    # left, and how much time until the ttl resets
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
        return 'unos momentos'
    elif time > 3600:
        elapsed //= 3600
        if elapsed == 1:
            return 'una hora'
        else:
            return str(elapsed) + ' horas'
    elif time > 60:
        elapsed //= 60
        if elapsed == 1:
            return 'un minuto'
        else:
            return str(elapsed) + ' minutos'
    else:
        if elapsed == 1:
            return 'un segundo'
        else:
            return str(elapsed) + ' segundos'


def clean(text, replies=False, hashtags=False, rts=False, urls=False):
    text = text.replace('\n', ' ')
    text = text.replace('\r', ' ')
    text = unescape(text)

    if rts:
        text = re.sub(r'^RT @[a-zA-Z0-9_]+:\s', '', text)

    if replies:
        text = re.sub(r'@[a-zA-Z0-9_]+\s?', '', text)

    if hashtags:
        text = re.sub(r'#[a-zA-Z0-9_]+\s?', '', text)

    if urls:
        text = re.sub(r'https?://.*\s?', '', text)

    text = re.sub(r'\s+', ' ', text)
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
    else:
        ext = 'jpg'

    return 'images/image_{}_{}.{}'.format(hash_, kind, ext)


def decay(time, max_time, coeff):
    threshold = max_time - time
    if threshold < 0:
        threshold = 0
    return 1 + threshold * (coeff - 1) / max_time
