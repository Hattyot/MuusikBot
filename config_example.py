import os


BOT_TOKEN = ''

in_container = os.environ.get('IN_DOCKER', False)
if not in_container:
    MONGODB_URL = 'mongodb://127.0.0.1:27017'
    LAVALINK_HOST = '127.0.0.1'
else:
    MONGODB_URL = 'mongodb://mongodb_container:27017'
    LAVALINK_HOST = 'lavalink'

PREFIX = '>'
EMBED_COLOUR = 0x00a6ad
DEV_IDS = []

# Roles which cant use the bot commands
NON_DJS = []

# Spotify api
SPOTIFY_CLIENT_ID = ''
SPOTIFY_CLIENT_SECRET = ''

# Error server and channel where to send error messages
ERROR_SERVER = 0
ERROR_CHANNEL = 0
