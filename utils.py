from html import unescape
import re


def clean(text, replies=True, hashtags=False, rts=True, urls=False):
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

    text = text.replace('  ', ' ')
    text = text.strip()

    return text


def ellipsis(text, max_length):
    if len(text) > max_length:
        return text[:max_length - 1] + '…'
    else:
        return text
