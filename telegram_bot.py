import asyncio
import random

import telepot
import telepot.aio

from akari import Akari
from config import config
from image_search import ImageSearchNoResultsError
import utils


class TelegramBot(telepot.aio.Bot):
    HELP_MESSAGE = ("Hey! I'm Akari Shoah.\n"
                    'If you want an image, just tell me what do you want me '
                    'to search for.\n'
                    'You can also ask me to create GIFs for you on Twitter: '
                    'https://twitter.com/akari_shoah')
    HELP_MESSAGE_G = ("Hey! I'm Akari Shoah.\n"
                      'If you want an image, use the /akari command. For '
                      'example:\n/akari french fries')
    INVALID_CMD = ("I don't know what you mean by that. If you need help, "
                   'use /help.')
    COMPOSING_MSGS = ('Okay, hold on a second...',
                      'Wait a moment...',
                      "I'm working on it...",
                      "This shouldn't take long...",
                      'Hold on...',
                      "I'll see what I can do...",
                      'Sit tight...',
                      'Give me a moment...',
                      'Hmm, wait...')


    PRIVATE_CHATS = ('private',)
    PUBLIC_CHATS = ('group', 'supergroup')

    username = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._answerer = telepot.aio.helper.Answerer(self)
        self.username = config.get('telegram', 'username')

    async def on_chat_message(self, message):
        try:
            content_type, chat_type, chat_id, _, msg_id = \
                telepot.glance(message, long=True)

            # we only work with "text" messages
            if content_type != 'text':
                if chat_type in self.PRIVATE_CHATS:
                    # only do this if it's a privmsg
                    await self.send_message(message, self.INVALID_CMD,
                                            quote_msg_id=msg_id)
                return

            # we only work in private, groups and supergroups
            if chat_type not in self.PRIVATE_CHATS + self.PUBLIC_CHATS:
                return

            # get the name of the user and log it
            name = self.format_name(message)
            if not name:
                utils.logger.warning('Message without a "from" field received')
                return
            longname = '{chat_id} ({name})'.format(chat_id=chat_id, name=name)
            utils.logger.info('Message from %s: "%s"',
                              longname, message['text'])

            # commands need special handling
            if message['text'].startswith('/'):
                command, rest = self._get_command(message['text'])
                akari_commands = ('akari', 'akari@' + self.username)

                if command not in akari_commands:
                    if chat_type in self.PRIVATE_CHATS:
                        if command in ('help', 'start'):
                            msg = self.HELP_MESSAGE
                        else:
                            msg = self.INVALID_CMD
                        await self.send_message(message, msg, no_preview=True,
                                                quote_msg_id=msg_id)
                        return
                    elif chat_type in self.PUBLIC_CHATS:
                        return  # unknown cmd, this was meant for another bot
            else:
                rest = message['text'].strip()

            # if the resulting message is empty...
            if not rest:
                if chat_type in self.PUBLIC_CHATS:  # only show this in groups
                    await self.send_message(message, self.HELP_MESSAGE_G,
                                            quote_msg_id=msg_id)
                return

            # check rate limit if this chat id is not exempt from them
            exemptions = config.get('telegram', 'rate_limit_exemptions',
                                    type='int_list')
            if chat_id not in exemptions:
                rate_limit = utils.ratelimit_hit('telegram', chat_id)
                if not rate_limit['allowed']:
                    msg = 'Message from %s: throttled (resets in %d seconds)'
                    utils.logger.warning(msg, longname, rate_limit['reset'])
                    msg = ('Not so fast! Try again in %s.' %
                           utils.timedelta(rate_limit['reset']))
                    await self.send_message(message, msg,
                                            quote_msg_id=msg_id)
                    return

            msg = random.choice(self.COMPOSING_MSGS)
            await self.send_message(message, msg, quote_msg_id=msg_id)

            # first, search...
            try:
                akari = Akari(rest, type='animation', shuffle_results=True)
            except ImageSearchNoResultsError:
                await self.send_message(message, 'No results.',
                                        quote_msg_id=msg_id)
                return

            # then, if successful, send the pic
            utils.logger.info('Sending %s to %s', akari.filename, longname)
            await self.send_message(message, type='file',
                                    filename=akari.filename,
                                    quote_msg_id=msg_id)
        except Exception:
            utils.logger.exception('Error handling %s (%s)',
                                   longname, message['chat']['type'])
            await self.send_message(message, 'Sorry, try again.',
                                    quote_msg_id=msg_id)

    async def send_message(self, message, caption=None, filename=None,
                           type='text', no_preview=False,
                           quote_msg_id=None):
        """helper function to send messages to users."""
        if type == 'text':
            if not caption:
                raise ValueError('You need a caption parameter to send text')
            text = utils.ellipsis(caption, 4096)
            await self.sendMessage(message['chat']['id'], text,
                                   disable_web_page_preview=no_preview,
                                   reply_to_message_id=quote_msg_id)
        elif type == 'image':
            if not filename:
                raise ValueError('You need a file parameter to send an image')
            caption = utils.ellipsis(caption, 200)
            with open(filename, 'rb') as f:
                await self.sendPhoto(message['chat']['id'], f, caption=caption,
                                     reply_to_message_id=quote_msg_id)
        elif type == 'file':
            if not filename:
                raise ValueError('You need a file parameter to send a file')
            if caption:
                raise ValueError("You can't send a caption with a file")
            with open(filename, 'rb') as f:
                await self.sendDocument(message['chat']['id'], f,
                                        reply_to_message_id=quote_msg_id)

    @staticmethod
    def _get_command(text):
        command, _, rest = text.partition(' ')
        command = command[1:]
        rest = rest.strip()
        return command, rest

    @staticmethod
    def format_name(message):
        """formats a "from" property into a string"""
        if 'from' not in message:
            return None
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
