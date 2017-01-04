import json
import os
import re
import socket
import urllib
import uuid

from bs4 import BeautifulSoup
import requests
from wand.exceptions import ImageError, CorruptImageError, CoderError
from wand.image import Image

from config import config
import utils


class ImageSearchError(Exception):
    pass


class ImageSearchNoResultsError(Exception):
    pass


class GoogleImageSearch(object):
    def __init__(self, text):
        utils.logger.info('Starting Google image search: "%s"', text)

        url = 'https://www.google.es/search'
        params = {'tbm': 'isch', 'q': text}

        try:
            s = requests.session()
            s.mount('https://', requests.adapters.HTTPAdapter(max_retries=10))
            headers = {'User-Agent': config.get('image_search', 'user_agent')}
            response = s.get(url, params=params, headers=headers, timeout=3)
        except (requests.exceptions.RequestException, socket.timeout):
            raise ImageSearchError('Error making an HTTP request')

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

        results = []
        for result_json in results_json:
            image_url = urllib.parse.unquote(result_json['ou'])
            results.append((image_url, result_json['ru']))

        self.results = results


class ImageSearch(object):
    def __init__(self, text):
        self.results = []

        results = GoogleImageSearch(text).results

        if len(results) == 0:
            raise ImageSearchNoResultsError('No results found for "%s"' % text)

        for image_url, source_url in results:
            # check if the source is banned and, in that case, ignore it
            banned_sources = config.get('image_search', 'banned_sources',
                                        type=list)
            if (any(x in source_url for x in banned_sources) or
                    any(x in image_url for x in banned_sources)):
                continue

            self.results.append(ImageSearchResult(image_url, source_url, text))


class ImageSearchResultError(Exception):
    pass


class ImageSearchResult(object):
    def __init__(self, image_url, source_url, text):
        self.image_url = image_url
        self.source_url = source_url
        self.text = text
        self.hash = str(uuid.uuid4())

        self.filename = None  # will be populated after calling .download()

    def download(self):
        try:
            utils.logger.info('Downloading image "%s" from "%s"',
                              self.image_url, self.source_url)
            # fake the referrer
            response = requests.get(self.image_url,
                                    headers={'Referer': self.source_url},
                                    timeout=5)
        except (requests.exceptions.RequestException, socket.timeout):
            # if the download times out, try with the next result
            raise ImageSearchResultError('Timed out')

        # if the download fails (404, ...), try with the next result
        if response.status_code != requests.codes.ok:
            raise ImageSearchResultError('Download of image failed')

        # store the image
        filename = self.get_path('original')
        utils.logger.info('Saving image to "%s"', filename)
        with open(filename, 'wb') as handle:
            for block in response.iter_content(1048576):
                if not block:
                    break
                handle.write(block)

        # and a metadata file to know where it came from
        metafile = self.get_path('meta')
        with open(metafile, 'w') as handle:
            handle.write('url:\t' + self.image_url + '\n')
            handle.write('source:\t' + self.source_url + '\n')
            handle.write('query:\t' + self.text + '\n')

        # check the size of the image before loading it into memory
        if os.stat(filename).st_size > 25 * 1024 * 1024:
            raise ImageSearchResultError('Image too big')

        # try to get Wand to load it as an image. if that doesn't work, raise
        # an exception so that we try with the next result
        try:
            image = Image(filename=filename)
        except (ImageError, CorruptImageError, CoderError):
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
