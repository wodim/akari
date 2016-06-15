from hashlib import md5
import json
import os
import random
import requests
import socket

from config import config
import utils


def image_search(text, max_size=3072 * 1024):
    utils.logger.info('image_search(): "{}"'.format(text))

    # remove '
    text = text.replace("'", ' ')
    url = "https://api.datamarket.azure.com/Bing/Search/v1/Composite"
    params = {'Sources': "'image'",
              'Query': "'{}'".format(text),
              'Adult': "'Off'",
              'Market': "'{}'".format(config['bing']['market']),
              '$format': 'json'}

    try:
        api_key = random.choice(config['bing']['api_keys'])
        response = requests.get(url, auth=('', api_key), params=params)
    except (requests.exceptions.RequestException, socket.timeout) as e:
        raise Exception('Error al hacer la petición HTTP')

    if response.status_code != requests.codes.ok:
        utils.logger.warning('image_search(): response code not ok ({})'
                             .format(response.status_code))
        raise Exception('No pude hacer la búsqueda: error {}'
                        .format(response.status_code))

    try:
        decoded_json = json.loads(response.text)
    except:
        utils.logger.warning('image_search(): could not decode json response')
        raise Exception('Error al decodificar el JSON.')

    try:
        results = decoded_json['d']['results'][0]['Image']
    except KeyError:
        utils.logger.warning('image_search(): api response can not be parsed')
        raise Exception('Me he quedado sin gasolina.')

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
                                        headers={'Referer': source_url})
            except (requests.exceptions.RequestException, socket.timeout) as e:
                # if the download times out, try with the next result
                continue

            # if the download fails (404, ...), try with the next result
            if response.status_code != requests.codes.ok:
                utils.logger.warning('image_search(): download of image ' +
                                     'failed')
                continue

            sum = md5(bytearray(text, encoding="utf-8")).hexdigest()
            filename = 'images/image_{}.jpeg'.format(sum)

            with open(filename, 'wb') as handle:
                for block in response.iter_content(1048576):
                    if not block:
                        break
                    handle.write(block)
                handle.close()

            # if it's not an image (referrer trap, catch-all html 404...)
            # or if it's too big, try with the next result
            if (not mimetype.startswith('image/') or
                    os.stat(filename).st_size > max_size):
                utils.logger.warning('image_search(): image too big or not ' +
                                     'an image')
                continue

            utils.logger.info('image_search(): complete')
            return filename, source_url
    else:
        raise Exception('No hay resultados para "{}".'.format(text))
