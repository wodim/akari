class Cache(object):
    """a simple kv cache for some stuff that I don't mind losing upon
        restarts"""
    cache = {}

    def get(self, key):
        try:
            return self.cache[key]
        except KeyError:
            return None

    def set(self, key, value):
        self.cache[key] = value

    def __contains__(self, key):
        return key in self.cache


# this is a global, shared instance of Cache to be used by anybody
cache = Cache()
