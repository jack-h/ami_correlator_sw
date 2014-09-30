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

    opts, args = p.parse_args(sys.argv[1:])
    if args == []:
        config_file = None
    else:
        config_file = args[0]

    # initialise connection to correlator
    corr = AMI.AmiSbl(config_file=config_file, verbose=True, passive=True, skip_prog=True)
    time.sleep(0.1)

    for feng in corr.fengs:
        if feng.roachhost.host == 'alice':
            s = feng.get_spectra()
            if opts.plot:
                pylab.plot(s, label='ANT %d, %s band'%(feng.ant, feng.band))

    if opts.plot:
        pylab.legend()
        pylab.show()
