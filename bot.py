from tweepy.streaming import StreamListener
from tweepy import Stream

from akari import akari_search
from config import config
from image_search import image_search
from translate import translate
from twitter import api, auth
import utils


class StreamException(Exception):
    pass


class StreamWatcherListener(StreamListener):
    def on_status(self, status):
        utils.logger.info('{id} - "{text}" by {screen_name} via {source}'
                          .format(id=status.id,
                                  text=utils.clean(status.text),
                                  screen_name=status.author.screen_name,
                                  source=status.source))

        # ignore yourself
        if status.author.screen_name == config['twitter']['screen_name']:
            return

        # ignore those who are not talking to you
        if not '@' + config['twitter']['screen_name'] in status.text:
            if not hasattr(status, 'retweeted_status'):
                # if it is not a retweet store this status
                with open('pending.txt', 'a') as p_file:
                    text = utils.clean(status.text, urls=True, replies=True,
                                       rts=True)
                    p_file.write(text + '\n')
            return

        # ignore retweets
        if hasattr(status, 'retweeted_status'):
            return

        # follow the author if he's new
        if not status.author.following:
            api.create_friendship(status.author.screen_name)

        text, image = parse(status.text)

        # parser determined there's nothing to do about this status,
        # so we are done here
        if not text and not image:
            return

        # start building a reply. prepend @nick of whoever we are replying to
        reply = '@' + status.author.screen_name
        if text:
            reply += ' ' + text

        # post it
        # don't catch exceptions. in this case, it's better to let it crash
        # so the stream reconnects
        if image:
            reply = utils.ellipsis(reply, utils.MAX_STATUS_WITH_MEDIA_LENGTH)
            api.update_with_media(image, status=reply,
                                  in_reply_to_status_id=status.id)
        else:
            reply = utils.ellipsis(reply, utils.MAX_STATUS_LENGTH)
            api.update_status(reply, in_reply_to_status_id=status.id)

    def on_error(self, status_code):
        utils.logger.warning('An error has occured! Status code = {}'
                             .format(status_code))
        return True  # keep stream alive

    def on_timeout(self):
        print('Snoozing Zzzzzz')


def parse(text):
    try:
        parts = text.split(' ')[1:]
        command = parts[0]
        if command == 'traduce' or command == 'translate':
            text = translate(' '.join(parts[2:]), parts[1])
            return text, None
        elif command == 'imagen' or command == 'image':
            filename, source_url = image_search(' '.join(parts[1:]))
            return 'Aquí tienes (sacado de %s):' % source_url, filename
        else:
            text = ' '.join(parts).replace('akari ', '')
            filename, caption = akari_search(text)
            return caption, filename
    except IndexError:
        pass
    except Exception as e:
        return 'エラー： %s' % str(e), None

if __name__ == '__main__':
    try:
        listener = StreamWatcherListener()
        stream = Stream(auth, listener)
        stream.userstream()
    except KeyboardInterrupt:
        pass
