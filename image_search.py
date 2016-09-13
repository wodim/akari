import json
import os
import random
import requests
import socket
import uuid

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
            headers = {'User-Agent': config['google']['user_agent']}
            response = s.get(url, params=params, headers=headers,
                             timeout=3)
        except (requests.exceptions.RequestException, socket.timeout) as e:
            raise ImageSearchException('Error making an HTTP request')

        if response.status_code != requests.codes.ok:
            msg = 'Response code not ok ({})'.format(response.status_code)
            utils.logger.warning(msg)
            raise ImageSearchException(msg)

        try:
            from bs4 import BeautifulSoup
            import re

            soup = BeautifulSoup(response.text, 'html.parser')
            results_json = [json.loads(x.text) for x in
                            soup.find_all(class_=re.compile('_meta$'))]
        except Exception as e:
            msg = 'Could not decode response'
            utils.logger.exception(msg)
            raise ImageSearchException(msg)

        results = []
        for result_json in results_json:
            results.append({'image_url': result_json['ou'],
                            'source_url': result_json['ru']})

        self.results = results


class BingImageSearch(object):
    def __init__(self, text):
        utils.logger.info('Starting Bing image search: "{}"'.format(text))

        # escape '
        text = text.replace("'", "''")
        url = 'https://api.datamarket.azure.com/Bing/Search/v1/Composite'
        # if adult results are enabled, safesearch is off, else strict
        adult = "'Off'" if config['bing']['adult'] else "'Strict'"
        params = {'Sources': "'image'",
                  'Query': "'{}'".format(text),
                  'Adult': adult,
                  'Market': "'{}'".format(config['bing']['market']),
                  '$format': 'json'}

        try:
            # choose a random api key. keys that start with * are disabled.
            api_key = random.choice([x for x in config['bing']['api_keys']
                                    if not x.startswith('*')])
            s = requests.session()
            s.mount('https://', requests.adapters.HTTPAdapter(max_retries=10))
            response = s.get(url, auth=('', api_key), params=params,
                             timeout=3)
        except (requests.exceptions.RequestException, socket.timeout) as e:
            raise ImageSearchException('Error making an HTTP request')

        if response.status_code != requests.codes.ok:
            msg = 'Response code not ok ({})'.format(response.status_code)
            utils.logger.warning(msg)
            raise ImageSearchException(msg)

        try:
            decoded_json = json.loads(response.text)
        except Exception as e:
            msg = 'Could not decode response'
            utils.logger.exception(msg)
            raise ImageSearchException(msg)

        try:
            results_json = decoded_json['d']['results'][0]['Image']
        except KeyError:
            msg = 'API response could not be parsed'
            utils.logger.warning(msg)
            raise ImageSearchException(msg)

        results = []
        for result_json in results_json:
            results.append({'image_url': result_json['MediaUrl'],
                            'source_url': result_json['SourceUrl']})

        self.results = results


class ImageSearch(object):
    def __init__(self, text, provider=None, max_size=10 * 1024 * 1024):
        if provider not in ('google', 'bing'):
            if config['image_search']['provider'] in ('google', 'bing'):
                provider = config['image_search']['provider']
            else:
                provider = 'google'

        if provider == 'google':
            try:
                results = GoogleImageSearch(text).results
            except ImageSearchException as e:
                msg = 'Failed to search using Google, will fall back to Bing'
                utils.logger.exception(msg)
                results = BingImageSearch(text).results
        elif provider == 'bing':
            results = BingImageSearch(text).results

        if len(results) > 0:
            # shuffle the results
            random.shuffle(results)
            for result in results:
                image_url = result['image_url']
                source_url = result['source_url']

                # check if the source is banned and, in that case, ignore it
                if any(x in source_url
                       for x in config['image_search']['banned_sources']):
                    utils.logger.info('Skipping banned source: ' + source_url)
                    continue

                try:
                    utils.logger.info(('Downloading image "{image_url}" ' +
                                       'from "{source_url}"')
                                      .format(image_url=image_url,
                                              source_url=source_url))
                    # fake the referrer
                    response = requests.get(image_url,
                                            headers={'Referer': source_url},
                                            timeout=5)
                except (requests.exceptions.RequestException,
                        socket.timeout) as e:
                    # if the download times out, try with the next result
                    continue

                # if the download fails (404, ...), try with the next result
                if response.status_code != requests.codes.ok:
                    utils.logger.warning('Download of image failed')
                    continue

                self.hash = str(uuid.uuid4())

                # store the image
                filename = utils.build_path(self.hash, 'original')
                utils.logger.info('Saving image to "{filename}"'
                                  .format(filename=filename))
                with open(filename, 'wb') as handle:
                    for block in response.iter_content(1048576):
                        if not block:
                            break
                        handle.write(block)
                    handle.close()

                # and a metadata file to know where it came from
                metafile = utils.build_path(self.hash, 'meta')
                with open(metafile, 'w') as handle:
                    handle.write('url:\t' + image_url + '\n')
                    handle.write('source:\t' + source_url + '\n')
                    handle.write('query:\t' + text + '\n')

                # if it's not an image (referrer trap, catch-all html 404...)
                # or if it's too big, try with the next result
                try:
                    Image(filename=filename)
                except CorruptImageError as e:
                    utils.logger.warning('Not an image')
                    continue

                if os.stat(filename).st_size > max_size:
                    utils.logger.warning('Image too big')
                    continue

                utils.logger.info('Complete')
                return

        utils.logger.warning('No results')
        raise ImageSearchNoResultsException('No results found for "{}".'
                                            .format(text))
