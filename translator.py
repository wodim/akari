import html
import json
import requests
import socket

import utils


class TranslatorException(Exception):
    pass


class Translator(object):
    def __init__(self, text, lang_to, lang_from='es-ES'):
        url = 'http://mymemory.translated.net/api/ajaxfetch'
        params = {'q': text, 'langpair': '{}|{}'.format(lang_from, lang_to),
                  'mtonly': '1'}

        try:
            response = requests.get(url, params, timeout=5)
        except (requests.exceptions.RequestException, socket.timeout) as e:
            raise TranslatorException('Error al hacer la petición HTTP')

        try:
            decoded_json = json.loads(response.text)
        except:
            utils.logger.warning('Translator: api response can not be decoded')
            raise TranslatorException('Error al decodificar el JSON.')

        translation = decoded_json['responseData']['translatedText']

        if decoded_json['responseStatus'] != 200:
            if 'IS AN INVALID TARGET LANGUAGE' in translation:
                utils.logger.warning('Translator: incorrect language ({})'
                                     .format(decoded_json['responseStatus']))
                raise TranslatorException('El idioma que has elegido no es ' +
                                          'válido.')
            else:
                utils.logger.warning('Translator: response code not ok ({})'
                                     .format(decoded_json['responseStatus']))
                raise TranslatorException('Error al traducir.')

        if len(translation.strip()) == 0:
            utils.logger.warning('Translator: unsupported language')
            raise TranslatorException('El idioma no está soportado.')

        try:
            translation = decoded_json['responseData']['translatedText']
            translation = html.unescape(translation)
        except:
            utils.logger.warning('Translator: api response can not be parsed')
            raise TranslatorException('No va bien el tema.')

        translation = translation.replace('@ ', '@')

        self.translation = translation
