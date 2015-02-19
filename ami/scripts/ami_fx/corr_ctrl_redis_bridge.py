import sys
import time
import socket
import ami.ami as AMI
import ami.helpers as helpers
import ami.amisa_control as control
import signal
import logging
import struct
import redis
import numpy as np

logger = helpers.add_default_log_handlers(logging.getLogger(__name__))

def struct_to_redis(redis, struct, prefix='CONTROL:'):
    for entry in struct.entries:
        if isinstance(entry, control.UnpackableStruct):
            struct_to_redis(redis, entry, prefix=prefix+entry.varname+':')
        else:
            if entry.varname != 'dummy':
                redis.set(prefix + entry.varname, entry.val)
                print 'Writing to redis: Key', prefix+entry.varname, 'val:', entry.val

def signal_handler(signum, frame):
    try:
        ctrl.close_sockets()
    except:
        pass
    exit()

if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('%prog [options] [CONFIG_FILE]')
    p.add_option('-b', '--baseline', dest='baseline', type='string', default='0,0', 
        help='Baseline to send to control server -- NOT YET IMPLEMENTED')
    p.set_description(__doc__)

    opts, args = p.parse_args(sys.argv[1:])

    if args == []:
        config_file = None
    else:
        config_file = args[0]

    # This initiates connections to the ROACHs, which isn't really necessary
    corr = AMI.AmiDC()
    time.sleep(0.1)

    ctrl = control.AmiControlInterface(config_file=config_file)
    ctrl.connect_sockets()

    # first get some meta data, as this encodes the source name
    # which we will use to name the output file
    while (ctrl.try_recv() is None):
        print "Waiting for meta data"
        time.sleep(1)

    print "Got meta data"
    print "Current status", ctrl.meta_data.obs_status.val
    print "Current source", ctrl.meta_data.obs_def.name.val
    print "Current RA,dec", ctrl.meta_data.obsra.val, ctrl.meta_data.obsdec.val
    print "Current nsamp,HA", ctrl.meta_data.nsamp, ctrl.meta_data.ha_reqd.val


    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    last_corr_time = None
    corr_cnt = 0
    while(True):
        if(ctrl.try_recv() == 0):
            # bridge received meta data -> redis
	    print 'Writing Redis keys at time', time.time()
            struct_to_redis(corr.redis_host, ctrl.meta_data, prefix='CONTROL:')
            # bridge correlator data from redis -> control socket
            ts = corr.redis_host.get('RECEIVER:timestamp0')
            # Only check for new correlations if we have new meta data
            if ts != last_corr_time:
                corrdat = np.fromstring(redis.Redis.get(corr.redis_host, 'RECEIVER:xeng_raw0'), dtype=np.int32).reshape([corr.n_bands * 2048, corr.n_bls, 1, 2])
                corr_shape = corrdat.shape
                print 'Sending 1 baseline to control pc'
                ctrl.try_send(ts, 1, corr_cnt, corrdat[:,0,0,:].reshape(corr_shape[0]*2))
                last_corr_time = ts
                corr_cnt += 1
            
        time.sleep(0.1)
