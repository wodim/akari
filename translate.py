import html
import json
import requests
import socket

import utils


def translate(text, lang_to, lang_from='es-ES'):
    url = 'http://mymemory.translated.net/api/ajaxfetch'
    params = {'q': text, 'langpair': '{}|{}'.format(lang_from, lang_to),
              'mtonly': '1'}

    try:
        response = requests.get(url, params, timeout=5)
    except (requests.exceptions.RequestException, socket.timeout) as e:
        raise Exception('Error al hacer la petición HTTP')

    try:
        decoded_json = json.loads(response.text)
    except:
        utils.logger.warning('translate(): api response can not be decoded')
        raise Exception('Error al decodificar el JSON.')

    translation = decoded_json['responseData']['translatedText']

    if decoded_json['responseStatus'] != 200:
        if 'IS AN INVALID TARGET LANGUAGE' in translation:
            utils.logger.warning('translate(): incorrect language ({})'
                                 .format(decoded_json['responseStatus']))
            raise Exception('El idioma que has elegido no es válido.')
        else:
            utils.logger.warning('translate(): response code not ok ({})'
                                 .format(decoded_json['responseStatus']))
            raise Exception('Error al traducir.')

    if len(translation.strip()) == 0:
        utils.logger.warning('translate(): unsupported language')
        raise Exception('El idioma no está soportado.')

    try:
        translation = decoded_json['responseData']['translatedText']
        translation = html.unescape(translation)
    except:
        utils.logger.warning('translate(): api response can not be parsed')
        raise Exception('No va bien el tema.')

    translation = translation.replace('@ ', '@')

    return translation
