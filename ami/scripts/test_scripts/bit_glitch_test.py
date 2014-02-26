import numpy as np
import corr
import adc5g as adc
import time
import struct
import sys
import pylab
import ami.ami as AMI

ROACH = 'alice'
ADC=1
SNAP = 'feng_snapshot_adc%d'%ADC

corr = AMI.AmiDC(config_file=None, verbose=True, passive=False)

time.sleep(0.1)

COARSE_DELAY = 0
corr.all_fengs('phase_switch_enable',False)
corr.all_fengs('set_fft_shift',-1)
#corr.all_fengs('set_coarse_delay',COARSE_DELAY)

print "CALIBRATING AGAIN!"
corr.all_fengs('calibrate_adc',verbosity=2)
exit()
