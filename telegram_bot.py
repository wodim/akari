import asyncio

import telepot
import telepot.async

from akari import akari_search
from config import config
from image_search import ImageSearchException
import utils


class TelegramBotException(Exception):
    pass


class TelegramBot(telepot.async.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._answerer = telepot.async.helper.Answerer(self)

    async def on_chat_message(self, message):
        try:
            content_type, chat_type, chat_id = telepot.glance(message)

            # ignore this message if it is not text
            if content_type != 'text':
                return

            utils.logging.info(('Message from {chat_id} ({type}): ' +
                                '"{message_text}"')
                               .format(chat_id=chat_id,
                                       type=message['chat']['type'],
                                       message_text=message['text']))

            # check rate limit
            if chat_id not in config['telegram']['rate_limit_exempt_chat_ids']:
                rate_limit = utils.rate_limit.hit('telegram', chat_id)
                if not rate_limit['allowed']:
                    _msg = (('Message from {chat_id} ({type}): throttled ' +
                            '(resets in {reset} seconds)')
                            .format(chat_id=chat_id,
                                    type=message['chat']['type'],
                                    reset=rate_limit['reset']))
                    utils.logging.warn(_msg)
                    _msg = (('Echa el freno, Madaleno. Vuelve a intentarlo ' +
                            'en {}.')
                            .format(utils.timedelta(rate_limit['reset'])))
                    await self._send_reply(message, _msg)
                    return

            await self.sendChatAction(chat_id, 'upload_photo')
            filename, caption = self._process_chat_message(message['text'])
            await self._send_reply(message, caption, filename=filename)
        except ImageSearchException as e:
            utils.logging.exception('Error searching for {chat_id} ({type})'
                                    .format(chat_id=chat_id,
                                            type=message['chat']['type']))
            await self._send_reply(message, 'Error: ' + str(e))
        except Exception as e:
            utils.logging.exception('Error handling {chat_id} ({type})'
                                    .format(chat_id=chat_id,
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
            result = akari_search(text)
        except ImageSearchException as e:
            raise
        except Exception as e:
            raise TelegramBotException(str(e))

        return result

if __name__ == '__main__':
    bot = TelegramBot(config['telegram']['token'])

    loop = asyncio.get_event_loop()
    loop.create_task(bot.message_loop())

    try:
        loop.run_forever()
    finally:
        loop.close()
