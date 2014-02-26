import numpy as np
import corr
import adc5g as adc
import time
import struct
import sys

ROACH = '192.168.0.111'

r = corr.katcp_wrapper.FpgaClient(ROACH)
time.sleep(0.1)

adc.set_spi_register(r,0,0x05+0x80,0) #use counter mode
adc.set_test_mode(r, 0)
adc.set_test_mode(r, 1)
adc.sync_adc(r,zdok_0=True,zdok_1=False)

time.sleep(0.5)

Fpercore = 5./4. #GHz
i = 0

r.write_int('rst',1)
r.write_int('rst',0)

CORES = 4
glitches = np.zeros(CORES)
start_time = time.time()
while(True):
    for core in range(CORES):
        glitches[core] = r.read_uint('glitch_cnt%d'%core)
        if glitches[core] > 1e9:
            print "IMMINENT OVERFLOW. GTFO."
            exit()
    runtime = time.time() - start_time
    print "Glitches after %d seconds (%.2f GSa per core):"%(runtime,runtime*Fpercore), glitches
    sys.stdout.flush()
    time.sleep(1)
