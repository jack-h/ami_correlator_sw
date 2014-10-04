import redis
import socket
import time
import yaml
import json

def write_config_to_redis(configfile):
    with open(configfile, 'r') as fh:
        confstr = fh.read()

    conf = yaml.load(confstr)
    redis_host = conf['Configuration']['redis_host']
    redis_port = conf['Configuration']['redis_port']

    r = redis.Redis(redis_host, port=redis_port)
    r.hset('config', 'file', configfile)
    r.hset('config', 'host', socket.gethostname())
    r.hset('config', 'time', time.asctime(time.gmtime()))
    r.hset('config', 'unixtime', time.time())
    r.hset('config', 'conf', conf)
    r.hset('config', 'confstr', confstr)

class JsonRedis(redis.Redis):
    '''
    As redis.Redis, but read and write json strings
    '''

    def get(self, name):
        v = redis.Redis.get(self, name)
        if v is None:
            return None
        else:
            return json.loads(v)

    def set(self, name, value, **kwargs):
        '''
        JSONify the input and send to redis.
        Automatically send a key containing the
        update time, with keyname 'name:last_update_time:'
        '''
        redis.Redis.set(self, name, json.dumps(value), **kwargs)
        redis.Redis.set(self, name+':last_update_time', time.time())
        

    

