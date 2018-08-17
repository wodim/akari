import configparser
import re
import sys
from time import sleep

from cache import cache


class ConfigCacheMissError(Exception):
    pass


class Config(object):
    def __init__(self, filename, cached=True, retry=5):
        """cached: use cache
            retry: how many times to retry opening the config file if it's
                locked. there's a delay of 1 second between retries"""
        self.config = configparser.ConfigParser()
        self.filename = filename
        self.cached = cached
        self.retry = retry

        for _ in range(self.retry):
            try:
                with open(self.filename) as fp:
                    self.config.read_file(fp)
                return
            except FileNotFoundError:
                # pretend it's an empty file
                return
            except OSError:
                # file locked, try again in 1 second
                sleep(1)
        raise OSError("I couldn't open the config file after %d retries" %
                      self.retry)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self._save()

    def _save(self):
        for _ in range(self.retry):
            try:
                with open(self.filename, 'w') as fp:
                    self.config.write(fp)
                return
            except OSError:
                # file locked, try again in 1 second
                sleep(1)
        raise OSError("I couldn't open the config file after %d retries" %
                      self.retry)

    def _get(self, section, key):
        try:
            return self.config.get(section, key)
        except configparser.NoSectionError:
            raise KeyError('No such section')
        except configparser.NoOptionError:
            raise KeyError('No such option')

    def _get_bool(self, section, key):
        return self.config.getboolean(section, key)

    def _to_int(self, value):
        return int(value)

    def _to_list(self, value):
        if value.strip() == '':
            return []
        else:
            return [x.strip() for x in value.split(', ')]

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
        self._save()

    def get(self, section, key, type=str, default=None):
        try:
            return self._cache_get(section, key)
        except ConfigCacheMissError:
            try:
                if type in (int, 'int'):
                    ret = self._to_int(self._get(section, key))
                elif type in (list, 'list'):
                    ret = self._to_list(self._get(section, key))
                elif type == 're_list':
                    ret = self._to_re_list(self._get(section, key))
                elif type == 'int_list':
                    ret = self._to_int_list(self._get(section, key))
                elif type in (str, 'str'):
                    ret = self._to_str(self._get(section, key))
                elif type in (bool, 'bool'):
                    ret = self._get_bool(section, key)
                else:
                    raise ValueError('Unknown type: %s' % type)
                self._cache_set(section, key, ret)
                return ret
            except KeyError:
                return default


try:
    filename = sys.argv[1]
except IndexError:
    filename = 'config.ini'
config = Config(filename)


def cfg(key, config_handle=config):
    """small shorthand method for config.get. key is section:key:type
        where type is optional"""
    parts = key.split(':')
    if len(parts) == 3:
        section, key, type_ = parts
        return config_handle.get(section, key, type_)
    elif len(parts) == 2:
        section, key = parts
        return config_handle.get(section, key)
    else:
        raise ValueError('Malformed key: "%s"' % key)


def cfgs(key, value, config_handle=config):
    """small shorthand method for config.set. key is section:key; type is
        always str"""
    parts = key.split(':')
    if len(parts) == 2:
        section, key = parts
        return config_handle.set(section, key, value)
    else:
        raise ValueError('Malformed key: "%s"' % key)
