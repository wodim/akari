from tweepy.streaming import StreamListener
from tweepy import Stream

from akari import akari_search
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
        if status.author.screen_name == api._me.screen_name:
            return

        # ignore those who are not talking to you
        if not '@' + api._me.screen_name in status.text:
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

        text = utils.clean(status.text, replies=True, urls=True)

        if text == '':
            return

        try:
            image, text = akari_search(text)
        except Exception as e:
            text, image = str(e), None

        # start building a reply. prepend @nick of whoever we are replying to
        if text:
            reply = '@' + status.author.screen_name + ' ' + text
        else:
            reply = '@' + status.author.screen_name

        # post it
        try:
            if image:
                reply = utils.ellipsis(reply,
                                       utils.MAX_STATUS_WITH_MEDIA_LENGTH)
                api.update_with_media(image, status=reply,
                                      in_reply_to_status_id=status.id)
            else:
                reply = utils.ellipsis(reply, utils.MAX_STATUS_LENGTH)
                api.update_status(reply, in_reply_to_status_id=status.id)
        except Exception as e:
            utils.logger.error('Error posting: ' + str(e))

    def on_error(self, status_code):
        utils.logger.warning('An error has occured! Status code = {}'
                             .format(status_code))
        return True  # keep stream alive

    def on_timeout(self):
        print('Snoozing Zzzzzz')


if __name__ == '__main__':
    try:
        listener = StreamWatcherListener()
        stream = Stream(auth, listener)
        stream.userstream()
    except KeyboardInterrupt:
        pass
