import html
import json
import requests
import socket

import utils


class TranslatorException(Exception):
    pass


class Translator(object):
    def __init__(self, text, lang_to, lang_from):
        url = 'http://mymemory.translated.net/api/ajaxfetch'
        params = {'q': text,
                  'langpair': lang_from + '|' + lang_to,
                  'mtonly': '1'}

        utils.logger.info('Translating "{text}" from {lang_from} to {lang_to}'
                          .format(text=text, lang_from=lang_from,
                                  lang_to=lang_to))
        try:
            response = requests.get(url, params, timeout=5)
        except (requests.exceptions.RequestException, socket.timeout) as e:
            raise TranslatorException('Error making an HTTP request')

        try:
            decoded_json = json.loads(response.text)
            translation = decoded_json['responseData']['translatedText']
        except:
            msg = 'Could not decode json response'
            utils.logger.warning(msg)
            raise TranslatorException(msg)

        if decoded_json['responseStatus'] != 200:
            if 'IS AN INVALID TARGET LANGUAGE' in self.translation:
                msg = ('Incorrect language ({})'
                       .format(decoded_json['responseStatus']))
                utils.logger.warning(msg)
                raise TranslatorException(msg)
            else:
                msg = ('Response code not ok ({})'
                       .format(decoded_json['responseStatus']))
                utils.logger.warning(msg)
                raise TranslatorException(msg)

        if len(translation.strip()) == 0:
            msg = 'Unsupported language'
            utils.logger.warning(msg)
            raise TranslatorException(msg)

        translation = html.unescape(translation)
        translation = translation.replace('@ ', '@')

        self.translation = translation
