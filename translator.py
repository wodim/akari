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
        params = {'q': text,
                  'langpair': lang_from + '|' + lang_to,
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

        self.translation = decoded_json['responseData']['translatedText']

        if decoded_json['responseStatus'] != 200:
            if 'IS AN INVALID TARGET LANGUAGE' in self.translation:
                utils.logger.warning('Translator: incorrect language ({})'
                                     .format(decoded_json['responseStatus']))
                raise TranslatorException('El idioma que has elegido no es ' +
                                          'válido.')
            else:
                utils.logger.warning('Translator: response code not ok ({})'
                                     .format(decoded_json['responseStatus']))
                raise TranslatorException('Error al traducir.')

        if len(self.translation.strip()) == 0:
            utils.logger.warning('Translator: unsupported language')
            raise TranslatorException('No hay traducción para el texto.')

        self.translation = html.unescape(self.translation)
        self.translation = self.translation.replace('@ ', '@')
