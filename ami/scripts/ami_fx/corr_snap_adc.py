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

    n_plots = len(corr.fengs)
    x_plots = int(np.ceil(np.sqrt(n_plots)))
    y_plots = int(np.ceil(n_plots / float(x_plots)))
    stddevs = {}
    for fn,feng in enumerate(corr.fengs):
        adc = feng.snap('snapshot_adc', man_trig=True, format='b', wait_period=1)
        pylab.figure(0)
        pylab.subplot(x_plots,y_plots,fn+1)
        pylab.plot(adc)
        pylab.ylim((-2**7, 2**7))
        pylab.title('ADC values: ROACH %s, ADC %d, (ANT %d, BAND %s)'%(feng.roachhost.host,feng.adc,feng.ant,feng.band))
        pylab.figure(1)
        pylab.subplot(x_plots,y_plots,fn+1)
        pylab.hist(adc, bins=2**6, range=(-2**7, 2**7), normed=True)
        pylab.title('ADC values: ROACH %s, ADC %d, (ANT %d, BAND %s)'%(feng.roachhost.host,feng.adc,feng.ant,feng.band))
        print 'ANT %d %s band: stddev: %.3f'%(feng.ant, feng.band, np.std(adc))

    print ''
    pylab.show()

        


