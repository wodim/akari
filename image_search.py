import json
import os
import re
import socket
import uuid

from bs4 import BeautifulSoup
import requests
from wand.exceptions import CorruptImageError
from wand.image import Image

from config import config
import utils


class ImageSearchException(Exception):
    pass


class ImageSearchNoResultsException(Exception):
    pass


class GoogleImageSearch(object):
    def __init__(self, text):
        utils.logger.info('Starting Google image search: "{}"'.format(text))

        url = 'https://www.google.es/search'
        params = {'tbm': 'isch', 'q': text}

        try:
            s = requests.session()
            s.mount('https://', requests.adapters.HTTPAdapter(max_retries=10))
            headers = {'User-Agent': config.get('image_search', 'user_agent')}
            response = s.get(url, params=params, headers=headers,
                             timeout=3)
        except (requests.exceptions.RequestException, socket.timeout) as e:
            raise ImageSearchException('Error making an HTTP request')

        if response.status_code != requests.codes.ok:
            msg = 'Response code not ok ({})'.format(response.status_code)
            utils.logger.warning(msg)
            raise ImageSearchException(msg)

        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            results_json = [json.loads(x.text) for x in
                            soup.find_all(class_=re.compile('_meta$'))]
        except Exception as e:
            msg = 'Could not decode response'
            utils.logger.exception(msg)
            raise ImageSearchException(msg)

        results = []
        for result_json in results_json:
            results.append((result_json['ou'], result_json['ru']))

        self.results = results


class ImageSearch(object):
    def __init__(self, text):
        self.results = []

        results = GoogleImageSearch(text).results

        if len(results) == 0:
            utils.logger.warning('No results')
            msg = 'No results found for "%s"' % text
            raise ImageSearchNoResultsException(msg)

        for image_url, source_url in results:
            # check if the source is banned and, in that case, ignore it
            if any(x in source_url for x in
                   config.get('image_search', 'banned_sources', list)):
                continue

            self.results.append(ImageSearchResult(image_url, source_url, text))


class ImageResultErrorException(Exception):
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
            msg = ('Downloading image "{image_url}" from "{source_url}"'
                   .format(image_url=self.image_url,
                           source_url=self.source_url))
            utils.logger.info(msg)
            # fake the referrer
            response = requests.get(self.image_url,
                                    headers={'Referer': self.source_url},
                                    timeout=5)
        except (requests.exceptions.RequestException, socket.timeout) as e:
            # if the download times out, try with the next result
            raise ImageResultErrorException('Timed out')

        # if the download fails (404, ...), try with the next result
        if response.status_code != requests.codes.ok:
            raise ImageResultErrorException('Download of image failed')

        # store the image
        filename = utils.build_path(self.hash, 'original')
        utils.logger.info('Saving image to "{filename}"'
                          .format(filename=filename))
        with open(filename, 'wb') as handle:
            for block in response.iter_content(1048576):
                if not block:
                    break
                handle.write(block)

        # and a metadata file to know where it came from
        metafile = utils.build_path(self.hash, 'meta')
        with open(metafile, 'w') as handle:
            handle.write('url:\t' + self.image_url + '\n')
            handle.write('source:\t' + self.source_url + '\n')
            handle.write('query:\t' + self.text + '\n')

        # if it's not an image (referrer trap, catch-all html 404...)
        # or if it's too big, try with the next result
        try:
            Image(filename=filename)  # try to get Wand to load it as an image
        except CorruptImageError as e:
            raise ImageResultErrorException('Not an image')

        if os.stat(filename).st_size > 25 * 1024 * 1024:
            raise ImageResultErrorException('Image too big')

        utils.logger.info('Complete')
