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

glitches_a = []
glitches_b = []
glitches_c = []
glitches_d = []
for delay in range(32):
    print "setting delay", delay
    set_io_delay(r,0,0,delay)
    set_io_delay(r,0,1,delay)
    set_io_delay(r,0,2,delay)
    set_io_delay(r,0,3,delay)
    core_a, core_b, core_c, core_d = adc.get_test_vector(r, ['snapshot_adc0'])
    #for i in range(4096):
    #    print np.binary_repr(core_a[i],width=8),
    #    print np.binary_repr(core_b[i],width=8),
    #    print np.binary_repr(core_c[i],width=8),
    #    print np.binary_repr(core_d[i],width=8)
    #    print core_a[i],
    #    print core_b[i],
    #    print core_c[i],
    #    print core_d[i]
    glitches_a += [adc.total_glitches(core_a, 8)]
    glitches_b += [adc.total_glitches(core_b, 8)]
    glitches_c += [adc.total_glitches(core_c, 8)]
    glitches_d += [adc.total_glitches(core_d, 8)]

print "GLITCHES IN CORE A B C D BY IODELAY"
for delay in range(32):
    print "%2d %4d %4d %4d %4d"%(delay, glitches_a[delay], glitches_b[delay], glitches_c[delay], glitches_d[delay])


set_io_delay(r,0,0,13)#14)
set_io_delay(r,0,1,13)#14)
set_io_delay(r,0,2,13)#2)
set_io_delay(r,0,3,10)#10)
core_a, core_c, core_b, core_d = adc.get_test_vector(r, ['snapshot_adc0'])
print "core A glitches:", adc.total_glitches(core_a, 8)
print "core B glitches:", adc.total_glitches(core_b, 8)
print "core C glitches:", adc.total_glitches(core_c, 8)
print "core D glitches:", adc.total_glitches(core_d, 8)



opt0, glitches0 = adc.calibrate_mmcm_phase(r, 0, ['snapshot_adc0',])
#opt1, glitches1 = adc.calibrate_mmcm_phase(r, 1, ['snapshot_adc1',])
adc.unset_test_mode(r, 0)
adc.unset_test_mode(r, 1)
