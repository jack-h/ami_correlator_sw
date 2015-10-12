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
    p.add_option('-z', '--zero', dest='zero', action='store_true', default=False,
        help='Write delays with zeros and exit')
    p.add_option('-r', '--rate', dest='rate', type='int', default=60,
        help='Delays will be update at approximately this rate, in seconds. Default = 60.')

    opts, args = p.parse_args(sys.argv[1:])
    if args == []:
        config_file = None
    else:
        config_file = args[0]

    # initialise connection to correlator
    corr = AMI.AmiDC(config_file=config_file, passive=True, skip_prog=True)
    time.sleep(0.1)
    
    last_update_time = 0
    if opts.zero:
       update_time = corr.timed_coarse_delay_update(delays=[0]*corr.n_ants) 
       logger.info('Zero-ed delays at %s'%time.ctime(update_time))
       exit()
    else:
       while(True):
           while(time.time() < (last_update_time + opts.rate)):
               time.sleep(1)
           logger.info('Attempting to load new coefficients at time %s'%time.ctime(time.time()))
           last_update_time = corr.timed_coarse_delay_update(delays=corr.get_source_delays(adc_clks=True)) 
    
    
