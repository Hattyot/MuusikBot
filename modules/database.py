import pymongo
import config


class Connection:
    __slots__ = ['mongo_client', 'db', 'dj', 'timers']

    def __init__(self):
        self.mongo_client = pymongo.MongoClient(config.MONGODB_URL)
        self.db = self.mongo_client['Musikud']
        self.dj = self.db['dj']
        self.timers = self.db['timers']
