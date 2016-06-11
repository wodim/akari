import html
import json
import requests
import socket
import urllib


def translate(text, language):
    session = requests.session()
    url = ('http://mymemory.translated.net/api/ajaxfetch?q={text}' +
           '&langpair=es-ES|{lang}&mtonly=1')
    url = url.format(text=urllib.parse.quote_plus(text), lang=language)

    try:
        response = session.get(url)
    except (requests.exceptions.RequestException, socket.timeout) as e:
        raise Exception('Error al hacer la petición HTTP')

    try:
        decoded_json = json.loads(response.text)
    except:
        raise Exception('Error al decodificar el JSON.')

    translation = decoded_json['responseData']['translatedText']

    if decoded_json['responseStatus'] != 200:
        if 'IS AN INVALID TARGET LANGUAGE' in translation:
            raise Exception('El idioma que has elegido, "{}", no es válido.'
                            .format(language))
        else:
            raise Exception('Error al traducir.')

    if len(translation.strip()) == 0:
        raise Exception('El idioma "{}" no está soportado.'
                        .format(language))

    try:
        translation = decoded_json['responseData']['translatedText']
        translation = html.unescape(translation)
    except:
        raise Exception('No va bien el tema.')

    translation = translation.replace('@ ', '@')

    return translation
