import asyncio

import telepot
import telepot.async

from akari import akari_search
from config import config
import utils


class BotException(Exception):
    pass


class AkariBot(telepot.async.Bot):
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

            await self.sendChatAction(chat_id, 'upload_photo')
            filename, caption = self._process_chat_message(message['text'])
            await self._send_reply(message, caption, filename=filename)
        except Exception as e:
            try:
                exception_string = str(e)
            except:
                exception_string = '???'
            finally:
                utils.logging.info(('Error sent to {chat_id} ({type}): ' +
                                    '{exception}')
                                   .format(chat_id=chat_id,
                                           type=message['chat']['type'],
                                           exception=exception_string))
                error_message = 'Error: ' + exception_string
                await self._send_reply(message, error_message)

    async def _send_reply(self, message, caption, filename=None):
        if filename:
            f = open(filename, 'rb')
            await self.sendPhoto(message['chat']['id'],
                                 f, caption=caption)
        else:
            await self.sendMessage(message['chat']['id'],
                                   caption)

    def _process_chat_message(self, text):
        try:
            result = akari_search(text)
        except Exception as e:
            raise BotException(str(e))

        return result

if __name__ == '__main__':
    bot = AkariBot(config['telegram']['token'])

    loop = asyncio.get_event_loop()
    loop.create_task(bot.message_loop())

    try:
        loop.run_forever()
    finally:
        loop.close()
