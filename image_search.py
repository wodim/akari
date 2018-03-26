import hashlib
import json
import os
import re
import socket
import urllib

from bs4 import BeautifulSoup
import requests
from wand.image import Image

from config import cfg
import utils


class ImageSearchError(Exception):
    pass


class ImageSearchNoResultsError(Exception):
    pass


def google_image_search(text):
    utils.logger.info('Starting Google image search: "%s"', text)

    url = 'https://www.google.com/search'
    params = {'tbm': 'isch', 'q': text}

    try:
        sess = requests.Session()
        sess.mount('https://', requests.adapters.HTTPAdapter(max_retries=10))
        headers = {'User-Agent': cfg('image_search:user_agent')}
        response = sess.get(url, params=params, headers=headers, timeout=3)
    except (requests.exceptions.RequestException, socket.timeout):
        raise ImageSearchError('Error making an HTTP request')
    finally:
        sess.close()

    if response.status_code != requests.codes.ok:
        raise ImageSearchError('Response code not ok (%d)' %
                               response.status_code)

    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        results_json = [json.loads(x.text) for x in
                        soup.find_all(class_=re.compile('_meta$'))]
    except Exception:
        msg = 'Could not decode response'
        utils.logger.exception(msg)
        raise ImageSearchError(msg)
    finally:
        soup.decompose()

    results = []
    for result_json in results_json:
        image_url = urllib.parse.unquote(result_json['ou'])
        results.append((image_url, result_json['ru']))

    return results


# this should be \b, but hyphens are considered to be part of the word
regex_remove_not = re.compile(r'(\W)-')


@utils.memoize('image_search', timeout=60 * 60 * 8)
def image_search(text):
    # remove leading hyphens from words
    text = regex_remove_not.sub(r'\1', text)
    results = google_image_search(text)

    if not results:
        raise ImageSearchNoResultsError('No results found for "%s"' % text)

    res = []
    for image_url, source_url in results:
        # check if the source is banned and, in that case, ignore it
        banned_sources = cfg('image_search:banned_sources:list')
        if (any(x in source_url for x in banned_sources) or
                any(x in image_url for x in banned_sources)):
            continue

        res.append(ImageSearchResult(image_url, source_url, text))

    return res


class ImageSearchResultError(Exception):
    pass


class ImageSearchResult(object):
    def __init__(self, image_url, source_url, text):
        self.image_url = image_url
        self.source_url = source_url
        self.text = text
        self.hash = hashlib.md5(image_url.encode('utf-8')).hexdigest()
        self.filename = None  # will be populated after calling .download()

    def download(self):
        self.filename = self.get_path('original')
        if os.path.isfile(self.filename):
            utils.logger.info('Returning cached file "%s".', self.image_url)
            return

        try:
            utils.logger.info('Downloading image "%s" from "%s"',
                              self.image_url, self.source_url)
            headers = {'Accept': '*/*',
                       'User-Agent': cfg('image_search:user_agent'),
                       'Referer': self.source_url}
            response = requests.get(self.image_url, headers=headers, timeout=5)
        except (requests.exceptions.RequestException, socket.timeout):
            # if the download times out, try with the next result
            raise ImageSearchResultError('Timed out')

        # if the download fails (404, ...), try with the next result
        if response.status_code != requests.codes.ok:
            raise ImageSearchResultError('Download of image failed')

        # store the image
        utils.logger.info('Saving image to "%s"', self.filename)
        with open(self.filename, 'wb') as handle:
            for block in response.iter_content(1024 * 1024):
                if not block:
                    break
                handle.write(block)

        # and a metadata file to know where it came from
        metafile = self.get_path('meta')
        with open(metafile, 'w') as fp:
            print('url:    %s' % self.image_url, file=fp)
            print('source: %s' % self.source_url, file=fp)
            print('query:  %s' % self.text, file=fp)

        # check the size of the image before loading it into memory
        if os.stat(self.filename).st_size > 25 * 1024 * 1024:
            raise ImageSearchResultError('Image too big')

        # try to get Wand to load it as an image. if that doesn't work, raise
        # an exception so that we try with the next result
        try:
            image = Image(filename=self.filename)
        except Exception:
            raise ImageSearchResultError('Not an image')
        else:
            image.destroy()

        utils.logger.info('Complete')

    def get_path(self, kind):
        if kind == 'meta':
            ext = 'txt'
        elif kind == 'animation':
            ext = 'gif'
        else:
            ext = 'jpg'

        return 'images/image_%s_%s.%s' % (self.hash, kind, ext)
