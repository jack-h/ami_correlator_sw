import sys
import os
import time
import struct
import numpy as np
import pylab
import socket
import ami.ami as AMI
from ami.helpers import uint2int, dbs

if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('%prog [options] [CONFIG_FILE]')
    p.set_description(__doc__)
    p.add_option('-p', '--plot', dest='plot', action='store_true', default=False,
        help='Show plots. Default: False')
    p.add_option('-m', '--monitor', dest='monitor', action='store_true', default=False,
        help='Monitor continuously')

    opts, args = p.parse_args(sys.argv[1:])
    if args == []:
        config_file = None
    else:
        config_file = args[0]

    # initialise connection to correlator
    corr = AMI.AmiSbl(config_file=config_file, passive=True, skip_prog=True)
    time.sleep(0.1)

    # turn on the noise switch
    a = corr.all_fengs_multithread('noise_switch_enable', True)
    print corr.redis_host

    while(True):
        tic = time.time()
        spectra = corr.all_fengs_multithread('get_spectra', autoflip=True)
        time.sleep(1)
        eq = corr.all_fengs('get_eq', redishost=corr.redis_host, autoflip=True, per_channel=True)
        toc = time.time()
        print 'New data acquired in time:', toc - tic
        for fn, feng in enumerate(corr.fengs):
            key = 'STATUS:noise_demod:ANT%d_%s'%(feng.ant, feng.band)
            d = spectra[fn] * np.abs(eq[fn])**2
            corr.redis_host.set(key, d.tolist())
        time.sleep(0.25)
        if not opts.monitor:
            break

    if opts.plot:
        pylab.figure(0)
        for fn, feng in enumerate(corr.fengs):
            pylab.subplot(2,2,fn+1)
            pylab.plot(spectra[fn])

        pylab.show()
