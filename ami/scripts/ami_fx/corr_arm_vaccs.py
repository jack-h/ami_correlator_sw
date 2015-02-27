import sys
import os
import time
import numpy as np
import ami.ami as AMI

if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('%prog [options] [CONFIG_FILE]')
    p.set_description(__doc__)
    p.add_option('-t', '--time', dest='time', type='float', default=5.0,
        help='Number of seconds in the future to arm vaccs')

    opts, args = p.parse_args(sys.argv[1:])
    if args == []:
        config_file = None
    else:
        config_file = args[0]

    # initialise connection to correlator
    corr = AMI.AmiDC(config_file=config_file, passive=True)
    time.sleep(0.1)
    
    corr.arm_vaccs(time.time() + opts.time)
    [xeng.reset_gbe() for xeng in corr.xengs]
    cur_mcnt = corr.xengs[0].read_uint('xeng_mcnt_out')
    print 'Current xeng out mcnt:', cur_mcnt, cur_mcnt>>12

