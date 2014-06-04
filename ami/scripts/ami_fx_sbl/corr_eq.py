import sys
import os
import time
import struct
import numpy as np
import adc5g as adc
import pylab
import socket
import ami.ami as AMI
from ami.helpers import uint2int, dbs
import cPickle as pickle

def calc_eq_factor(d, target_power, snap_bits=18, quant_bits=4):
    bit_diff = snap_bits - quant_bits
    target_bits = target_power + bit_diff
    return np.sqrt(1./d) * 2**target_bits

def format_eq(eq, bits=16, bp=6):
    # convert the EQ into appropriately scaled integers
    # which will be correctly interpretted on the FPGA
    ints = np.round(eq*(2**bp))
    # saturate (coefficients are signed)
    ints[ints>2**(bits-1) - 1] = 2**(bits-1) - 1
    # pack as binary string
    eq_str = ''
    for v in ints:
        eq_str += struct.pack('>h',v)
        eq_str += struct.pack('>h',v)
    return eq_str

if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('%prog [options] [CONFIG_FILE]')
    p.set_description(__doc__)
    p.add_option('-N', '--samples', dest='samples', type='int', default=1,
        help='Number of snaps to average over. Default=1')
    p.add_option('-t', '--targetpower', dest='targetpower', type='float', default=0.1,
        help='Mean power target in LSBs. Default:0.1')
    p.add_option('-c', '--cutoff', dest='cutoff', type='float', default=10.,
        help='Set a cutoff level for <cutoff> EQ coefficients. Coefficients >[cutoff]*mean coefficient will be set to zero. Default:10')
    p.add_option('--new', dest='new', action='store_true', default=False,
        help='Use this flag to generate new coefficients. Otherwise, existing coefficients will be used unless they don\'t exist')
    p.add_option('-p', '--plot', dest='plot', action='store_true', default=False,
        help='Show plots. Default: False')

    opts, args = p.parse_args(sys.argv[1:])
    load_new = opts.new
    if args == []:
        config_file = None
    else:
        config_file = args[0]

    # initialise connection to correlator
    corr = AMI.AmiSbl(config_file=config_file, verbose=True, passive=True)
    time.sleep(0.1)

    # load the existing coefficients
    base_dir = os.path.dirname(corr.config_file)
    base_name = os.path.basename(corr.config_file)
    coeff_file = base_dir + "/eq_" + base_name.split(".xml")[0]+".pkl"
    coeffs = {}
    if not load_new:
        print "trying to load EQ coefficients from %s"%coeff_file
        try:
            fh = open(coeff_file,'r')
            coeffs = pickle.load(fh)
            fh.close()
        except:
            print "Couldn't load coefficients. Computing new ones"
            load_new = True

    
    decimation=2
    vec_width = corr.n_chans/decimation
    for feng in corr.fengs:
        if load_new:
            print "Computing new coefficients"
            d = np.zeros(vec_width)
            for n in range(opts.samples):
                print '%d: Snapping data from ANT: %d, BAND: %s'%(n,feng.ant,feng.band)
                dlo = feng.snap('fft_low_snap',format='Q')[0:vec_width/2]/(2.**34) # normalise to 1 (data is 18_17 the converted to power, UFix36_34)
                dhi = feng.snap('fft_high_snap',format='Q')[0:vec_width/2]/(2.**34)
                #  This weird assignment is a firmware mess up. fix it
                d[0:vec_width:4] += dlo[0::2]
                d[1:vec_width:4] += dlo[1::2]
                d[2:vec_width:4] += dhi[0::2]
                d[3:vec_width:4] += dhi[1::2]
            d /= 1024. #there is an inherent accumulation of 1024 spectra on the FPGA
            pylab.figure(1)
            pylab.plot(dbs(d/opts.samples),label='ANT %d, BAND %s'%(feng.ant,feng.band))
            pylab.legend()
            pylab.title("Autocorrelation Passbands")
            pylab.ylabel("Power (db)")
            pylab.xlabel("Decimated Channel Number")

            # calculate target mean power, scaled for 4 bits
            mean_power = d / opts.samples
            eq = (np.sqrt(1./mean_power)) * opts.targetpower
            eq[eq>np.mean(eq)*opts.cutoff] = 0
            pylab.figure(2)
            pylab.plot(eq,label='ANT %d, BAND %s'%(feng.ant,feng.band))
            pylab.title("EQ coefficients")
            pylab.ylabel("Amplitude (linear)")
            pylab.xlabel("Decimated Channel Number")
            pylab.legend()
            # save eq in a dictionary ready for pickling
            coeffs['ANT%d_%s'%(feng.ant,feng.band)] = eq

        else:
            eq = coeffs['ANT%d_%s'%(feng.ant,feng.band)]

        eq_str = format_eq(eq,bits=16,bp=6)
        feng.write('eq', eq_str)
        rb = struct.unpack('>1024H', feng.read('eq',1024*2))
        #pylab.figure(3)
        #pylab.plot(rb,label='ANT %d, BAND %s'%(feng.ant,feng.band))
        #pylab.title("EQ coefficients")
        #pylab.ylabel("Amplitude (linear)")
        #pylab.xlabel("Decimated Channel Number")
        #pylab.legend()

        print "Grabbing snapshot of quantized signal for Antenna %d %s band"%(feng.ant,feng.band)
        quant = uint2int(feng.snap('quant_snap',format='B',wait_period=3),4,3,complex=True)[0:corr.n_chans]
        pylab.figure(4)
        pylab.plot(np.imag(quant),label='ANT %d, BAND %s'%(feng.ant,feng.band))
        pylab.title("Quantized signal (real part) (normalised to 1)")
        pylab.ylabel("Amplitude (linear)")
        pylab.xlabel("Channel Number")
        pylab.legend()


    # save new coeffs if there are some
    if load_new:
        print "Saving new coefficients to %s"%coeff_file
        fh = open(coeff_file,'w')
        pickle.dump(coeffs,fh)
        fh.close()

    if opts.plot:
        pylab.show()
