import asyncio

import telepot
import telepot.async

from akari import Akari
from config import config
from image_search import ImageSearchException
import utils


class TelegramBotException(Exception):
    pass


class TelegramBot(telepot.async.Bot):
    HELP_MESSAGE = ('¡Hola! Soy Akari Endlösung.\n' +
                    'Si quieres una imagen, sólo tienes que decirme qué ' +
                    'quieres buscar.\n' +
                    'También puedes pedirme imágenes en Twitter: ' +
                    'https://twitter.com/akari_endlosung')
    INVALID_CMD = ('No sé lo que quieres decir. Si necesitas ayuda, escribe ' +
                   '/help.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._answerer = telepot.async.helper.Answerer(self)

    async def on_chat_message(self, message):
        try:
            content_type, chat_type, chat_id = telepot.glance(message)

            # ignore this message if it is not text
            if content_type != 'text':
                return

            longname = '{chat_id} ({name})'.format(chat_id=chat_id,
                                                   name=self._name(message))
            utils.logging.info(('Message from {longname} ({type}): ' +
                                '"{message_text}"')
                               .format(longname=longname,
                                       type=message['chat']['type'],
                                       message_text=message['text']))

            if message['text'].startswith('/'):
                command = message['text'].split(' ')[0][1:]
                if command == 'help':
                    _msg = self.HELP_MESSAGE
                elif command == 'start':
                    _msg = self.HELP_MESSAGE
                else:
                    _msg = self.INVALID_CMD
                await self._send_reply(message, _msg)
                return

            # check rate limit
            if chat_id not in config['telegram']['rate_limit_exempt_chat_ids']:
                rate_limit = utils.rate_limit.hit('telegram', chat_id)
                if not rate_limit['allowed']:
                    _msg = (('Message from {longname} ({type}): throttled ' +
                            '(resets in {reset} seconds)')
                            .format(longname=longname,
                                    type=message['chat']['type'],
                                    reset=rate_limit['reset']))
                    utils.logging.warn(_msg)
                    _msg = (('Echa el freno, Madaleno. Vuelve a intentarlo ' +
                            'en {}.')
                            .format(utils.timedelta(rate_limit['reset'])))
                    await self._send_reply(message, _msg)
                    return

            await self.sendChatAction(chat_id, 'upload_photo')
            akari = self._process_chat_message(message['text'])
            await self._send_reply(message,
                                   akari.caption,
                                   filename=akari.filename)
        except ImageSearchException as e:
            utils.logging.exception('Error searching for {longname} ({type})'
                                    .format(longname=longname,
                                            type=message['chat']['type']))
            await self._send_reply(message, 'Error: ' + str(e))
        except Exception as e:
            utils.logging.exception('Error handling {longname} ({type})'
                                    .format(longname=longname,
                                            type=message['chat']['type']))
            await self._send_reply(message, 'Ha ocurrido un error.')

    async def _send_reply(self, message, caption, filename=None):
        if filename:
            caption = utils.ellipsis(caption, 200)
            f = open(filename, 'rb')
            await self.sendPhoto(message['chat']['id'],
                                 f, caption=caption)
        else:
            await self.sendMessage(message['chat']['id'],
                                   caption)

    def _process_chat_message(self, text):
        try:
            akari = Akari(text)
        except ImageSearchException as e:
            raise
        except Exception as e:
            raise TelegramBotException(str(e))

        return akari

    def _name(self, message):
        longname = []
        if 'username' in message['from']:
            longname.append('@' + message['from']['username'])
        if 'first_name' in message['from']:
            longname.append(message['from']['first_name'])
        if 'last_name' in message['from']:
            longname.append(message['from']['last_name'])
        return ', '.join(longname)


if __name__ == '__main__':
    bot = TelegramBot(config['telegram']['token'])

    loop = asyncio.get_event_loop()
    loop.create_task(bot.message_loop())

    try:
        loop.run_forever()
    finally:
        loop.close()
