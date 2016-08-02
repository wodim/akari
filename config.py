import json
import re
import sys

try:
    filename = sys.argv[1]
except IndexError:
    filename = 'config.json'

with open(filename) as config_file:
    config = json.load(config_file)

compiled_text_blacklist = []
for i in config['twitter']['text_blacklist']:
    compiled_text_blacklist.append(re.compile(i, re.IGNORECASE))
config['twitter']['text_blacklist'] = compiled_text_blacklist
