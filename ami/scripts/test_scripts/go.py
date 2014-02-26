import numpy as np
import corr
import adc5g as adc
import time
import struct

ROACH = '192.168.0.111'

r = corr.katcp_wrapper.FpgaClient(ROACH)
time.sleep(0.1)

print adc.calibrate_all_delays(r,0,verbosity=2)
print adc.get_core_offsets(r)
exit()
