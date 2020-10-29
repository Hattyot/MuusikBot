import pymongo
import config


class Connection:
    def __init__(self):
        self.mongo_client = pymongo.MongoClient(config.MONGODB_URL)
        self.db = self.mongo_client['Musikud']
        self.dj = self.db['dj']
        self.timers = self.db['timers']
        self.playlists = self.db['playlists']
