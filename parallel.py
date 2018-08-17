from queue import Queue
import threading


class Parallel(object):
    def __init__(self, func, things, num_threads):
        self.queue = Queue()

        for thing in things:
            self.queue.put(thing)

        for _ in range(num_threads):
            thread = threading.Thread(target=func, args=(self.queue,))
            thread.daemon = True
            thread.start()

    def start(self):
        self.queue.join()
