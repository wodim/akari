from configparser import ConfigParser
import re
import sys

from cache import cache


class Config(object):
    def __init__(self, filename):
        self.config = ConfigParser()
        self.config.read(filename)

    def _get(self, section, key):
        return self.config.get(section, key)

    def _get_bool(self, section, key):
        return self.config.getboolean(section, key)

    def _to_int(self, value):
        return int(value)

    def _to_list(self, value):
        if value.strip() == '':
            return []
        else:
            return [x.strip() for x in value.split(',')]

    def _to_int_list(self, value):
        return [int(x) for x in self._to_list(value)]

    def _to_re_list(self, value):
        return [re.compile(x, re.IGNORECASE) for x in self._to_list(value)]

    def _to_str(self, value):
        return value.strip()

    def _to_bool(self, value):
        return value

    def _cache_get(self, section, key):
        return cache.get('%s:%s' % (section, key))

    def _cache_set(self, section, key, value):
        return cache.set('%s:%s' % (section, key), value)

    def get(self, section, key, type=str):
        r = self._cache_get(section, key)

        if not r:  # cache miss
            if type == int:
                r = self._to_int(self._get(section, key))
            elif type == list:
                r = self._to_list(self._get(section, key))
            elif type == 're_list':
                r = self._to_re_list(self._get(section, key))
            elif type == 'int_list':
                r = self._to_int_list(self._get(section, key))
            elif type == str:
                r = self._to_str(self._get(section, key))
            elif type == bool:
                r = self._get_bool(section, key)
            self._cache_set(section, key, r)

        return r


try:
    filename = sys.argv[1]
except IndexError:
    filename = 'config.ini'
config = Config(filename)
