from hashlib import md5
import json
import os
import random
import requests
import socket
import urllib

from config import config


def image_search(text, max_size=3072 * 1024):
    session = requests.session()

    # remove '
    text = text.replace("'", ' ')
    url = ("https://api.datamarket.azure.com/Bing/Search/v1/Composite" +
           "?Sources=%27image%27&Query=%27{text}%27&Adult=%27Off%27" +
           "&Market=%27{market}%27&$format=json")
    url = url.format(text=urllib.parse.quote_plus(text),
                     market=config['bing']['market'])

    try:
        api_key = random.choice(config['bing']['api_keys'])
        response = session.get(url, auth=('', api_key))
    except (requests.exceptions.RequestException, socket.timeout) as e:
        raise Exception('Error al hacer la petición HTTP')

    if response.status_code != requests.codes.ok:
        raise Exception('No pude hacer la búsqueda: error {}'
                        .format(response.status_code))

    try:
        decoded_json = json.loads(response.text)
    except:
        raise Exception('Error al decodificar el JSON.')

    try:
        results = decoded_json['d']['results'][0]['Image']
    except KeyError:
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
                continue

            session = requests.session()
            try:
                # fake the referrer
                response = session.get(image_url,
                                       headers={'Referer': source_url})
            except (requests.exceptions.RequestException, socket.timeout) as e:
                # if the download times out, try with the next result
                continue

            # if the download fails (404, ...), try with the next result
            if response.status_code != requests.codes.ok:
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
                continue

            return filename, source_url
    else:
        raise Exception('No hay resultados para "{}".'.format(text))
