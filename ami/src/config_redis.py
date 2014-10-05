import redis
import socket
import time
import yaml
import json
import logging

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
        

'''
A Redis-based log handler from:
http://charlesleifer.com/blog/using-redis-pub-sub-and-irc-for-error-logging-with-python/
'''
class RedisHandler(logging.Handler):
    def __init__(self, channel, conn, *args, **kwargs):
        logging.Handler.__init__(self, *args, **kwargs)
        self.channel = channel
        self.redis_conn = conn

    def emit(self, record):
        attributes = [
            'name', 'msg', 'levelname', 'levelno', 'pathname', 'filename',
            'module', 'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
            'thread', 'threadName', 'process', 'processName',
        ]
        record_dict = dict((attr, getattr(record, attr)) for attr in attributes)
        record_dict['formatted'] = self.format(record)
        try:
            self.redis_conn.publish(self.channel, json.dumps(record_dict))
        except redis.RedisError:
            pass
    

