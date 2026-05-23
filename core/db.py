import os
from peewee import *
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db = SqliteDatabase(os.path.join(BASE_DIR, 'data', 'warmap.db'))

class BaseModel(Model):
    class Meta:
        database = db

class Channel(BaseModel):
    telegram_id = IntegerField(unique=True)
    name = CharField()
    url = CharField()
    active = BooleanField(default=True)

class Event(BaseModel):
    timestamp = DateTimeField(default=datetime.utcnow)
    text = TextField()
    channel_name = CharField()
    channel_url = CharField()
    city = CharField(null=True)
    lat = FloatField(null=True)
    lon = FloatField(null=True)
    event_type = CharField(default='unknown')  # explosion, drone, missile, shot_down, flyover
    media_url = TextField(null=True)
    message_id = IntegerField(null=True)

def init_db():
    db.connect(reuse_if_open=True)
    db.create_tables([Channel, Event], safe=True)
    db.close()
