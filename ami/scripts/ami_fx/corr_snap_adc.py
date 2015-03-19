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

def add_gauss_fit(data):
    mean = np.mean(data)
    sigma = np.sqrt(np.var(data))
    x = np.linspace(min(data), max(data), 100)
    pylab.plot(x,pylab.normpdf(x,mean,sigma))

if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('%prog [options] [CONFIG_FILE]')
    p.set_description(__doc__)
    p.add_option('-c', '--per_core', dest='per_core',action='store_true', default=False,
        help='Plot histograms of each ADC core')
    p.add_option('-b', '--histbins', dest='histbins', type='int', default=2**6,
        help='Number of histogram bins. Default = 2**6')
    p.add_option('-n', '--nsnaps', dest='nsnaps', type='int', default=1,
        help='Number of 16ksample chunks to snap before doing stats. Default:1')

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
        adc = np.array([])
        for n in range(opts.nsnaps):
            adc = np.append(adc, feng.snap('snapshot_adc', man_trig=True, format='b', wait_period=1))
        pylab.figure(0)
        pylab.subplot(x_plots,y_plots,fn+1)
        pylab.plot(adc)
        pylab.ylim((-2**7, 2**7))
        pylab.title('ADC values: ROACH %s, ADC %d, (ANT %d, BAND %s)'%(feng.roachhost.host,feng.adc,feng.ant,feng.band))
        pylab.figure(1)
        pylab.subplot(x_plots,y_plots,fn+1)
        pylab.hist(adc, bins=opts.histbins, range=(-2**7, 2**7), normed=True)
        pylab.title('ADC values: ROACH %s, ADC %d, (ANT %d, BAND %s)'%(feng.roachhost.host,feng.adc,feng.ant,feng.band))
        add_gauss_fit(adc)

        if opts.per_core:
            for i in range(4):
                pylab.figure(2+i)
                pylab.suptitle('Core %d'%i)
                pylab.subplot(x_plots,y_plots,fn+1)
                pylab.hist(adc[i::4], bins=opts.histbins, range=(-2**7, 2**7), normed=True)
                add_gauss_fit(adc[i::4])
                pylab.title('ADC values: ROACH %s, ADC %d, (ANT %d, BAND %s)'%(feng.roachhost.host,feng.adc,feng.ant,feng.band))

        print 'ANT %d %s band: Mean: %.3f, sigma: %.3f'%(feng.ant, feng.band, np.mean(adc), np.sqrt(np.var(adc)))
        if opts.per_core:
            for i in range(4):
                print '    Core %d: Mean: %.3f, sigma: %.3f'%(i, np.mean(adc[i::4]), np.sqrt(np.var(adc[i::4])))

    print ''
    pylab.show()


        


