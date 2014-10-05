import redis
import json
import time

r = redis.Redis('ami_redis_host')

ps = r.pubsub()

ps.subscribe('log-channel')

while(True):
    try:
        mess = ps.get_message(ignore_subscribe_messages=True)
        if mess is not None:
            print json.loads(mess['data'])['formatted']
        else:
            time.sleep(0.01)
    except KeyboardInterrupt:
        ps.close()
        exit()

