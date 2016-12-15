import asyncio

import telepot
import telepot.aio

from akari import Akari
from config import config
from image_search import ImageSearchNoResultsException
import utils


class TelegramBotException(Exception):
    pass


class TelegramBot(telepot.aio.Bot):
    HELP_MESSAGE = ("Hey! I'm Akari Shoah.\n"
                    'If you want an image, just tell me what do you want me '
                    'to search for.\n'
                    'You can also ask me to create GIFs for you on Twitter: '
                    'https://twitter.com/akari_shoah')
    INVALID_CMD = ("I don't know what you mean by that. If you need help, "
                   'use /help.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._answerer = telepot.aio.helper.Answerer(self)

    async def on_chat_message(self, message):
        try:
            content_type, chat_type, chat_id = telepot.glance(message)

            if content_type != 'text':
                await self.send_message(message, self.INVALID_CMD)
                return

            name = self.format_name(message)
            longname = '{chat_id} ({name})'.format(chat_id=chat_id,
                                                   name=name)
            utils.logger.info('Message from {longname}: "{message_text}"'
                              .format(longname=longname,
                                      message_text=message['text']))

            if message['text'].startswith('/'):
                command = message['text'].split(' ')[0][1:]
                if command == 'help':
                    msg = self.HELP_MESSAGE
                elif command == 'start':
                    msg = self.HELP_MESSAGE
                else:
                    msg = self.INVALID_CMD
                await self.send_message(message, msg, no_preview=True)
                return

            # check rate limit
            exemptions = config.get('telegram', 'rate_limit_exemptions',
                                    'int_list')
            if chat_id not in exemptions:
                rate_limit = utils.ratelimit_hit('telegram', chat_id)
                if not rate_limit['allowed']:
                    msg = (('Message from {longname}: throttled ' +
                            '(resets in {reset} seconds)')
                           .format(longname=longname,
                                   reset=rate_limit['reset']))
                    utils.logger.warning(msg)
                    msg = ('Not so fast! Try again in {}.'
                           .format(utils.timedelta(rate_limit['reset'])))
                    await self.send_message(message, msg)
                    return

            await self.sendChatAction(chat_id, 'upload_photo')

            # first, search...
            try:
                akari = Akari(message['text'], type='still',
                              shuffle_results=True)
            except ImageSearchNoResultsException:
                utils.logger.exception('Error searching for ' + longname)
                await self.send_message(message, 'No results.')
                return

            # then, if successful, send the pic
            await self.send_message(message, akari.caption,
                                    filename=akari.filename)
        except Exception as e:
            utils.logger.exception('Error handling {longname} ({type})'
                                   .format(longname=longname,
                                           type=message['chat']['type']))
            await self.send_message(message, 'Sorry, try again.')

    async def send_message(self, message, caption, filename=None,
                           no_preview=False):
        """helper function to send messages to users."""
        if filename:
            caption = utils.ellipsis(caption, 200)
            with open(filename, 'rb') as f:
                await self.sendPhoto(message['chat']['id'], f, caption=caption)
        else:
            caption = utils.ellipsis(caption, 4096)
            await self.sendMessage(message['chat']['id'], caption,
                                   disable_web_page_preview=no_preview)

    def format_name(self, message):
        """formats a "from" property into a string"""
        longname = []
        if 'username' in message['from']:
            longname.append('@' + message['from']['username'])
        if 'first_name' in message['from']:
            longname.append(message['from']['first_name'])
        if 'last_name' in message['from']:
            longname.append(message['from']['last_name'])
        return ', '.join(longname)


if __name__ == '__main__':
    bot = TelegramBot(config.get('telegram', 'token'))

    loop = asyncio.get_event_loop()
    loop.create_task(bot.message_loop())

    try:
        loop.run_forever()
    finally:
        loop.close()
