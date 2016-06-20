import json
import sys

try:
    filename = sys.argv[1]
except IndexError:
    filename = 'config.json'

with open(filename) as config_file:
    config = json.load(config_file)
