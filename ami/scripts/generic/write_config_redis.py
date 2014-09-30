import ami.config_redis as config_redis
import sys
import os

args = sys.argv[1:]

if args == []:
    config_file = os.environ.get('AMI_DC_CONF')
else:
    config_file = args[0]

print 'Configuration file is:', config_file

if not os.path.exists(config_file):
    print 'Config file does not exist!'
    exit()

config_redis.write_config_to_redis(config_file)

