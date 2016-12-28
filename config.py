import configparser
import re
import sys

from cache import cache


class ConfigCacheMissError(Exception):
    pass


class Config(object):
    def __init__(self, filename, cached=True):
        self.config = configparser.ConfigParser()
        self.filename = filename
        self.cached = cached

        try:
            with open(self.filename) as fp:
                self.config.read_file(fp)
        except FileNotFoundError:
            # pretend it's an empty file
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        with open(self.filename, 'w') as fp:
            self.config.write(fp)

    def _get(self, section, key):
        try:
            return self.config.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            raise KeyError('No such section')

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

    def _to_config_str(self, value):
        if isinstance(value, list):
            return ', '.join(value)
        else:
            return str(value)

    def _cache_get(self, section, key):
        if not self.cached:
            raise ConfigCacheMissError('caching is disabled')

        ret = cache.get('%s:%s' % (section, key))
        if not ret:
            raise ConfigCacheMissError('key not in cache')
        return ret

    def _cache_set(self, section, key, value):
        if self.cached:
            return cache.set('%s:%s' % (section, key), value)

    def set(self, section, key, value):
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, self._to_config_str(value))

    def get(self, section, key, type=str):
        try:
            return self._cache_get(section, key)
        except ConfigCacheMissError:
            if type == int:
                ret = self._to_int(self._get(section, key))
            elif type == list:
                ret = self._to_list(self._get(section, key))
            elif type == 're_list':
                ret = self._to_re_list(self._get(section, key))
            elif type == 'int_list':
                ret = self._to_int_list(self._get(section, key))
            elif type == str:
                ret = self._to_str(self._get(section, key))
            elif type == bool:
                ret = self._get_bool(section, key)
            self._cache_set(section, key, ret)
            return ret


try:
    filename = sys.argv[1]
except IndexError:
    filename = 'config.ini'
config = Config(filename)
