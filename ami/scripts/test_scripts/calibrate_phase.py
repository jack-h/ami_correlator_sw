import numpy as np
import corr
import adc5g as adc
import time
import struct

def set_io_delay(r,zdok,core,delay,regname='adc5g_controller'):
    ADC_BITS = 8
    for i in range(ADC_BITS):
        data_pin = (core<<3) + i
        reg_val = (delay<<24) + (data_pin<<16) + 0x01
        reg_val_str = struct.pack('>L',reg_val)
        r.blindwrite(regname,reg_val_str,offset=((4+zdok)*4))
        r.blindwrite(regname,reg_val_str,offset=((4+zdok)*4))
        #print np.binary_repr(r.read_int(regname,offset=6))


ROACH = '192.168.0.111'

r = corr.katcp_wrapper.FpgaClient(ROACH)
time.sleep(0.1)

adc.set_spi_register(r,0,0x05+0x80,0) #use strobing test mode
adc.set_test_mode(r, 0)
adc.set_test_mode(r, 1)
adc.sync_adc(r,zdok_0=True,zdok_1=False)


opt0, glitches0 = adc.calibrate_mmcm_phase(r, 0, ['snapshot_adc0',])
#opt1, glitches1 = adc.calibrate_mmcm_phase(r, 1, ['snapshot_adc1',])
adc.unset_test_mode(r, 0)
adc.unset_test_mode(r, 1)
