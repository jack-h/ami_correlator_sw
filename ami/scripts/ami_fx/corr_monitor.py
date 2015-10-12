import sys
import os
import time
import struct
import numpy as np
import pylab
import socket
import ami.ami as AMI
from ami.helpers import uint2int, dbs, add_default_log_handlers
import logging

logger = add_default_log_handlers(logging.getLogger("%s:%s"%(__file__,__name__)))

if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('%prog [options] [CONFIG_FILE]')
    p.set_description(__doc__)
    p.add_option('-p', '--plot', dest='plot', type='int', default=0,
        help='Number of grabs to do before showing plots. Default = 0 = do not plot.')
    p.add_option('-e', '--expire', dest='expire', type='int', default=5,
        help='Expiry time of redis keys in seconds. Default = 5. 0 = do not expire')
    p.add_option('-m', '--monitor', dest='monitor', action='store_true', default=False,
        help='Monitor continuously')

    opts, args = p.parse_args(sys.argv[1:])
    if args == []:
        config_file = None
    else:
        config_file = args[0]

    if opts.expire == 0:
        expire_time = None
    else:
        expire_time = opts.expire

    # initialise connection to correlator
    corr = AMI.AmiDC(config_file=config_file, passive=True, skip_prog=True)
    time.sleep(0.1)

    # turn on the noise switch
    print 'attempting to turn on noise switches'
    a = corr.all_fengs('noise_switch_enable', True)
    print 'done'

    grab_n = 0
    x = np.zeros_like(corr.all_fengs_multithread('get_spectra', autoflip=False))
    while(True):
        tic = time.time()
        print 'grabbing spectra'
        spectra = corr.all_fengs_multithread('get_spectra', autoflip=False)
        print 'getting EQ from redis'
        eq = corr.all_fengs('get_eq', redishost=corr.redis_host, autoflip=False, per_channel=True)
        toc = time.time()
        print 'New data acquired in time:', toc - tic
        for fn, feng in enumerate(corr.fengs):
            key = 'STATUS:noise_demod:ANT%d_%s'%(feng.ant, feng.band)
            d = spectra[fn] * np.abs(eq[fn])**2
            corr.redis_host.set(key, d.tolist(), ex=expire_time)
        logger.info('New monitor data sent at time %.2f'%time.time())
        print opts.plot, grab_n
        if opts.plot != 0:
            x += spectra * np.abs(eq)**2
            grab_n += 1
            if grab_n == opts.plot:
                break

        if (opts.plot == 0) and not opts.monitor:
            break

    if opts.plot:
        pylab.figure(0)
        for fn, feng in enumerate(corr.fengs):
            #pylab.subplot(2,2,fn+1)
            pylab.plot(x[fn], label='Ant %d, %s band'%(feng.ant, feng.band))

        pylab.legend()
        pylab.show()
