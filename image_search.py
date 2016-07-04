import json
import os
import random
import requests
import socket
import uuid

from config import config
import utils


class ImageSearchException(Exception):
    pass


def image_search(text, max_size=3072 * 1024):
    utils.logger.info('image_search(): "{}"'.format(text))

    # escape '
    text = text.replace("'", "''")
    url = "https://api.datamarket.azure.com/Bing/Search/v1/Composite"
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
        response = requests.get(url, auth=('', api_key), params=params,
                                timeout=5)
    except (requests.exceptions.RequestException, socket.timeout) as e:
        raise ImageSearchException('Error al hacer la petición HTTP')

    if response.status_code != requests.codes.ok:
        utils.logger.warning('image_search(): response code not ok ({})'
                             .format(response.status_code))
        raise ImageSearchException('No pude hacer la búsqueda: error {}'
                                   .format(response.status_code))

    try:
        decoded_json = json.loads(response.text)
    except:
        utils.logger.warning('image_search(): could not decode json response')
        raise ImageSearchException('Error al decodificar el JSON.')

    try:
        results = decoded_json['d']['results'][0]['Image']
    except KeyError:
        utils.logger.warning('image_search(): api response can not be parsed')
        raise ImageSearchException('Me he quedado sin gasolina.')

    if len(results) > 0:
        # shuffle the results
        random.shuffle(results)
        for result in results:
            image_url = result['MediaUrl']
            source_url = result['SourceUrl']
            mimetype = result['ContentType']

            # check if the source is banned and, in that case, ignore it
            if any(x in source_url for x in config['bing']['banned_sources']):
                utils.logger.info('image_search(): skipping banned source ' +
                                  '"{}"'.format(source_url))
                continue

            try:
                utils.logger.info('image_search(): downloading image ' +
                                  '"{image_url}" from "{source_url}"'
                                  .format(image_url=image_url,
                                          source_url=source_url))
                # fake the referrer
                response = requests.get(image_url,
                                        headers={'Referer': source_url},
                                        timeout=5)
            except (requests.exceptions.RequestException, socket.timeout) as e:
                # if the download times out, try with the next result
                continue

            # if the download fails (404, ...), try with the next result
            if response.status_code != requests.codes.ok:
                utils.logger.warning('image_search(): download of image ' +
                                     'failed')
                continue

            hash_ = str(uuid.uuid4())

            # store the image
            filename = utils.build_path(hash_, 'original')
            with open(filename, 'wb') as handle:
                for block in response.iter_content(1048576):
                    if not block:
                        break
                    handle.write(block)
                handle.close()

            # and a metadata file to know where it came from
            metafile = utils.build_path(hash_, 'meta')
            with open(metafile, 'w') as handle:
                handle.write('url:\t' + image_url + '\n')
                handle.write('source:\t' + source_url + '\n')
                handle.write('query:\t' + text + '\n')

            # if it's not an image (referrer trap, catch-all html 404...)
            # or if it's too big, try with the next result
            if (not mimetype.startswith('image/') or
                    os.stat(filename).st_size > max_size):
                utils.logger.warning('image_search(): image too big or not ' +
                                     'an image')
                continue

            utils.logger.info('image_search(): complete')
            return hash_, source_url

    utils.logger.warning('image_search(): no results')
    raise ImageSearchException('No hay resultados para "{}".'.format(text))
