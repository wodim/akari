from html import unescape
import logging
import re

MAX_STATUS_LENGTH = 140
MAX_STATUS_WITH_MEDIA_LENGTH = 116


class Logger(object):

    def __init__(self):
        logging.basicConfig(format='%(asctime)s: %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S',
                            level=logging.INFO)
        self.logger = logging.getLogger('akari_endlosung')

    def get_logger(self):
        return self.logger

logger = Logger().get_logger()
logger.info('Logger initialised.')


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
