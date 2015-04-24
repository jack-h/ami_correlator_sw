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
import pylab

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

def gen_reduce_bl_order(nants):
    rv = []
    for i in range(nants):
        for j in range(i, nants):
            rv += [[i,j]]
    return rv

def gen_casper2reduce_bls(nants, blorder, reduce_order=None):
    rv = []
    if reduce_order is None:
        reduce_order = gen_reduce_bl_order(nants)
    for bl in reduce_order:
        for cn, cbl in enumerate(blorder):
            if (bl[0] == cbl[0]) and (bl[1] == cbl[1]):
                rv += [{'conj':False, 'bl':cn}]
            elif (bl[0] == cbl[0]) and (bl[1] == cbl[1]):
                rv += [{'conj':True, 'bl':cn}]
    return rv


if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('%prog [options] [CONFIG_FILE]')
    p.set_description(__doc__)

    opts, args = p.parse_args(sys.argv[1:])

    if args == []:
        config_file = None
    else:
        config_file = args[0]


    # This initiates connections to the ROACHs, which isn't really necessary
    corr = AMI.AmiDC()
    time.sleep(0.1)

    # get the correlator data from redis
    #BLS_TO_SEND = [[4,5]]
    #BLS_TO_SEND = [[4,5], [4,6], [5,6]]
    BLS_TO_SEND = [[0,1], [0,2], [0,3], [0,4], [0,5], [0,6], [0,7], [0,8], [0,9],
                   [1,2], [1,3], [1,4], [1,5], [1,6], [1,7], [1,8], [1,9],
                   [2,3], [2,4], [2,5], [2,6], [2,7], [2,8], [2,9],
                   [3,4], [3,5], [3,6], [3,7], [3,8], [3,9],
                   [4,5], [4,6], [4,7], [4,8], [4,9],
                   [5,6], [5,7], [5,8], [5,9],
                   [6,7], [6,8], [6,9],
                   [7,8], [7,9],
                   [8,9]]
    corrdat = np.fromstring(redis.Redis.get(corr.redis_host, 'RECEIVER:xeng_raw0'), dtype=np.int32).reshape([corr.n_bands * 2048, corr.n_bls, 1, 2])
    corrdat_txbuf = np.zeros_like(corrdat[:, range(len(BLS_TO_SEND)), :, :])
    reduce_bl_order = gen_casper2reduce_bls(corr.n_ants, corr.bl_order, reduce_order=BLS_TO_SEND)
    print 'REDUCE baseline order:', reduce_bl_order

    ctrl = control.AmiControlInterface(config_file=config_file, rain_gauge=True)
    # hack the number of baselines to the correct size
    ctrl.data = control.DataStruct(n_chans=2*2048, n_bls=len(BLS_TO_SEND), n_ants=corr.n_ants, rain_gauge=True)
    ctrl.connect_sockets()

    # first get some meta data, as this encodes the source name
    # which we will use to name the output file
    while (ctrl.try_recv() is None):
        print "Waiting for meta data"
        time.sleep(1)

    print "Got meta data"
    print "Current status", ctrl.meta_data.obs_status.val
    print "Current source", ctrl.meta_data.obs_def.name.val
    print "Current RA,dec", ctrl.meta_data.smp_ra.val, ctrl.meta_data.smp_dec.val
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
            #if ts != last_corr_time:
            corrdat = np.fromstring(redis.Redis.get(corr.redis_host, 'RECEIVER:xeng_raw0'), dtype=np.int32).reshape([corr.n_bands * 2048, corr.n_bls, 1, 2])
            for bln, bl in enumerate(reduce_bl_order):
                corrdat_txbuf[:,bln,:,:] = corrdat[:,bl['bl'],:,:]
                if bl['conj']:
                    corrdat_txbuf[:,bln,:,0] *= -1
            rain_gauge = corr.noise_switched_from_redis()
            #pylab.subplot(3,1,1)
            #pylab.plot(rain_gauge[4])
            for i in range(corr.n_ants):
                for bn, bl in enumerate(corr.bl_order):
                    if bl == (4,4): #must be tuple, not list
                        rain_gauge[i] /= corrdat[:,bn,0,1]
                        rain_gauge[i][corrdat[:,bn,0,1]==0] = 0
            rain_gauge *= 1e10 #vaguely scale to unity
            #pylab.subplot(3,1,3)
            #pylab.plot(rain_gauge[4])
            #pylab.show()
            #rain_gauge = np.arange(corr.n_ants * corr.n_bands * 2048, dtype=np.float32)
                      
            print 'Sending baselines to control pc'
            #pylab.plot(corrdat[:, baseline_n, 0, :])
            #pylab.show()
            ctrl.try_send(ts, 1, corr_cnt, corrdat_txbuf.transpose([1,0,2,3]).flatten(), rain_gauge)
            #for ln, l in enumerate(corrdat_txbuf.transpose([1,0,2,3]).flatten()):
            #    print ln//2, l
            print 'sent'
            last_corr_time = ts
            corr_cnt += 1
            
        time.sleep(0.1)
