from html import unescape
import logging
import re

import redis

MAX_STATUS_LENGTH = 140
MAX_STATUS_WITH_MEDIA_LENGTH = 116


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


class RateLimit(object):
    def __init__(self):
        self.server = redis.Redis(socket_connect_timeout=1)
        try:
            self.server.ping()
            logger.warning('Redis initialised.')
            self.server_available = True
        except Exception as e:
            logger.warning('Redis server unavailable: ' + str(e))
            self.server_available = False

    # returns a tuple: whether the action was accepted, how many requests are
    # left, and how much time until the ttl resets
    def hit(self, prefix, user, max=10, ttl=60 * 10):
        def r(x, y, z): return {'allowed': x, 'left': y, 'reset': z}
        # if the server is not available, let it through
        if not self.server_available:
            return r(True, 1, 0)

        key = str(prefix) + ':' + str(user)
        value = self.server.get(key)

        if not value:
            # if key does not exist...
            self.server.set(key, 1)
            self.server.expire(key, ttl)
            return r(True, max - 1, ttl)
        else:
            current_ttl = self.server.ttl(key)
            if int(value) >= max:
                return r(False, 0, current_ttl)
            else:
                self.server.incr(key)
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
    text = re.sub(r'\s+', ' ', text)
    text = unescape(text)
    text = text.strip()

    if rts:
        text = re.sub(r'^RT @[a-zA-Z0-9_]+:\s', '', text)

    if replies:
        text = re.sub(r'@[a-zA-Z0-9_]+\s?', '', text)

    if hashtags:
        text = re.sub(r'#[a-zA-Z0-9_]+\s?', '', text)

    if urls:
        text = re.sub(r'https?://.*\s?', '', text)

    return text


def ellipsis(text, max_length):
    if len(text) > max_length:
        return text[:max_length - 1] + '…'
    else:
        return text
