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

    opts, args = p.parse_args(sys.argv[1:])
    if args == []:
        config_file = None
    else:
        config_file = args[0]

    # initialise connection to correlator
    corr = AMI.AmiDC(config_file=config_file)
    time.sleep(0.1)

    for feng in corr.fengs:
        feng.noise_switch_enable(False)

    s = corr.do_for_all('get_spectra', corr.fengs) #flush one to give time for the noise switch state to chance
    s = corr.do_for_all('get_spectra', corr.fengs)
    for fn, feng in enumerate(corr.fengs):
        pylab.plot(dbs(s[fn]), label='ANT %d, %s band'%(feng.ant+1, feng.band))

    for feng in corr.fengs:
        feng.noise_switch_enable(True)

    pylab.ylabel('Power (dB)')
    pylab.legend()
    pylab.show()
