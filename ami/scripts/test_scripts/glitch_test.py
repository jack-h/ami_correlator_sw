import numpy as np
import corr
import adc5g as adc
import time
import struct
import sys
import pylab
from optparse import OptionParser

p = OptionParser()
p.set_usage('%prog [options] [CONFIG_FILE]')
p.set_description(__doc__)
p.add_option('-r', '--roach', dest='roach',type='string', default='alice', 
    help='roach. Default: alice')
p.add_option('-z', '--zdok', dest='zdok',type='int', default=0, 
    help='zdok. Default: 0')

opts, args = p.parse_args(sys.argv[1:])

ROACH = opts.roach
ADC=opts.zdok

def graycode(n):
    if n==1:
        return np.array([0,1])
    else:
        g = graycode(n-1)
        return np.concatenate((g,g[::-1]+(1<<(n-1))))

gray = graycode(8) #an 8 bit gray encoder

r = corr.katcp_wrapper.FpgaClient(ROACH)
time.sleep(0.1)

adc.set_spi_register(r,0,0x05+0x80,0) #use counter mode
adc.set_spi_register(r,1,0x05+0x80,0) #use counter mode
adc.set_test_mode(r, 0)
adc.set_test_mode(r, 1)
adc.sync_adc(r,zdok_0=True,zdok_1=True)

time.sleep(0.5)

#opt0, glitches0 = adc.calibrate_mmcm_phase(r, ADC, ['feng_snapshot_adc%d'%ADC,])
#print opt0, glitches0

CORES = 4
glitches = np.zeros([CORES])

#for i in range(1000000):
i = 0
while(True):
    try:
        test_vec = np.array(adc.get_test_vector(r, ['feng_snapshot_adc%d'%ADC]))
        #pylab.subplot(2,1,1)
        #[pylab.plot(test_vec[core]) for core in range(4)]
        #pylab.subplot(2,1,2)
        #[pylab.plot(gray[test_vec[core]]) for core in range(4)]
        #pylab.show()
        for core in range(CORES):
            glitches[core] += adc.total_glitches(test_vec[core],8)
        #for j in range(100):
        #    for core in range(CORES):
        #        print "%3d"%test_vec[core,j],
        #    print ''

        print "Glitches after %d runs:"%i, glitches
        i += 1
        sys.stdout.flush()
    except KeyboardInterrupt:
        print "unsetting test mode and leaving"
        adc.unset_test_mode(r, 0)
        adc.unset_test_mode(r, 1)
        exit()
