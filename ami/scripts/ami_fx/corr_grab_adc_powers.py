import sys
import time
import numpy as np
import adc5g as adc
import pylab
import socket
import ami.ami as AMI
import ami.helpers as helpers
import struct

if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('%prog [options] [CONFIG_FILE]')
    p.set_description(__doc__)
    p.add_option('-n', '--noise', dest='noise_switch',action='store_true', default=False,
        help='Use the noise switches. Default = False')

    opts, args = p.parse_args(sys.argv[1:])

    if args == []:
        config_file = None
    else:
        config_file = args[0]

    # construct the correlator object, which will parse the config file and try and connect to
    # the roaches
    # If passive is True, the connections will be made without modifying
    # control software. Otherwise, the connections will be made, the roaches will be programmed and control software will be reset to 0.
    corr = AMI.AmiSbl(config_file=config_file, passive=True, skip_prog=True)
    time.sleep(0.1)

    if opts.noise_switch:
        scale_factor = 2
    else:
        scale_factor = 1

    for feng in corr.fengs:
        feng.noise_switch_enable(opts.noise_switch)

    #wait a couple of integrations to flush data with the wrong noise switch state
    corr.fengs[0].get_adc_power()
    corr.fengs[0].get_adc_power()

    for feng in corr.fengs:
        print '%15s, ADC %d (ANT:%d, BAND:%s): %f'%(feng.host, feng.adc, feng.ant+1, feng.band, np.sqrt(scale_factor*feng.get_adc_power()))

        


