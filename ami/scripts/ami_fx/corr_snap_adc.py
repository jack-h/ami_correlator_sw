import sys
import time
import numpy as np
import adc5g as adc
import pylab
import socket
import ami.ami as AMI
import ami.helpers as helpers
import struct
import scipy.stats

if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('%prog [options] [CONFIG_FILE]')
    p.set_description(__doc__)
    p.add_option('-c', '--per_core', dest='per_core',action='store_true', default=False,
        help='Plot histograms of each ADC core')

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
        pylab.hist(adc, bins=2**5, range=(-2**7, 2**7), normed=True)
        pylab.title('ADC values: ROACH %s, ADC %d, (ANT %d, BAND %s)'%(feng.roachhost.host,feng.adc,feng.ant,feng.band))

        if opts.per_core:
            pylab.figure(2)
            pylab.suptitle('Core 0')
            pylab.subplot(x_plots,y_plots,fn+1)
            pylab.hist(adc[0::4], bins=2**5, range=(-2**7, 2**7), normed=True)
            pylab.title('ADC values: ROACH %s, ADC %d, (ANT %d, BAND %s)'%(feng.roachhost.host,feng.adc,feng.ant,feng.band))

            pylab.figure(3)
            pylab.suptitle('Core 1')
            pylab.subplot(x_plots,y_plots,fn+1)
            pylab.hist(adc[1::4], bins=2**5, range=(-2**7, 2**7), normed=True)
            pylab.title('ADC values: ROACH %s, ADC %d, (ANT %d, BAND %s)'%(feng.roachhost.host,feng.adc,feng.ant,feng.band))

            pylab.figure(4)
            pylab.suptitle('Core 2')
            pylab.subplot(x_plots,y_plots,fn+1)
            pylab.hist(adc[2::4], bins=2**5, range=(-2**7, 2**7), normed=True)
            pylab.title('ADC values: ROACH %s, ADC %d, (ANT %d, BAND %s)'%(feng.roachhost.host,feng.adc,feng.ant,feng.band))

            pylab.figure(5)
            pylab.suptitle('Core 3')
            pylab.subplot(x_plots,y_plots,fn+1)
            pylab.hist(adc[3::4], bins=2**5, range=(-2**7, 2**7), normed=True)
            pylab.title('ADC values: ROACH %s, ADC %d, (ANT %d, BAND %s)'%(feng.roachhost.host,feng.adc,feng.ant,feng.band))

        print 'ANT %d %s band: Signal std dev: %.3f'%(feng.ant, feng.band, np.std(adc))

    print ''
    pylab.show()

        


