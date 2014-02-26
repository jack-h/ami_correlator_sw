import numpy as np
import corr
import adc5g as adc
import time
import struct

def set_io_delay(r,zdok,core,delay,bit='all',regname='adc5g_controller'):
    ADC_BITS = 8
    if bit == 'all':
        bit_range = range(ADC_BITS)
    else:
        bit_range = [bit]
    for i in bit_range:
        data_pin = (core<<3) + i
        reg_val = (delay<<24) + (data_pin<<16) + 0x01
        reg_val_str = struct.pack('>L',reg_val)
        r.blindwrite(regname,reg_val_str,offset=((4+zdok)*4))
        r.blindwrite(regname,reg_val_str,offset=((4+zdok)*4))
        #print np.binary_repr(r.read_int(regname,offset=6))

def glitches_by_bit(d,bit):
    SPACING = 11
    glitches = 0
    data = (np.array(d) & (1<<bit))>>bit
    last_index = None
    for i in range(len(d)):
        if data[i]==1:
            if (last_index is not None) and ((i-last_index) != SPACING):
                glitches += 1
            last_index = i
    return glitches

def select_best_delay(d,clk=625.,ref_clk=200.,ntaps=32):
    '''
    A method to set the best bitwise delays for an input data bus. We assume that all the inputs
    are approximately aligned to begin with. I.e. if the input bus is 8 bits, we assume that the relative delays
    of each bit are << 1 clock cycle.
        d is an [N_BITS x N_DELAY_TRIALS] array containing numbers of glitches

        1. Find the longest stretch of zero glitches. This becomes the scoring_box_size.
        2. Convolve a scoring_box_size window of ones with the glitches (per bit). The minima mark the best delays
        3. Since there will be multiple minima at high clock rates, choose the best one, by summing minima over different bits
    '''
    tap_delay = 1./ref_clk/float(ntaps)/2. #78ps for 200 MHz reference
    taps_per_cycle = (1./clk)/tap_delay/2. #This gives the number of taps in a complete clock cycle (1/2 because data is DDR)
    #First find the longest stretch of zero glitches.
    n_bits, n_delays = d.shape
    max_zeros = 0
    for bit in range(n_bits):
        n_zero = 0
        for delay in range(1,n_delays): #ignore the delay=0 value for ease of code
            if (d[bit,delay]) == 0:
                n_zero += 1
                if n_zero > max_zeros:
                    max_zeros = n_zero
            else:
                n_zero = 0
    print "Longest stretch of zero glitches:", max_zeros
    score = np.zeros([n_bits,n_delays-max_zeros+1])
    for bit in range(n_bits):
        score[bit] = np.convolve(np.ones(max_zeros), d[bit,:], mode='valid')

    for delay in range(n_delays-max_zeros+1):
        print "DELAY %2d:" %delay,
        for bit in range(n_bits):
            print "%4d"%score[bit,delay],
        print ''

ROACH = '192.168.0.111'

r = corr.katcp_wrapper.FpgaClient(ROACH)
time.sleep(0.1)

adc.set_spi_register(r,0,0x05+0x80,1) #use strobing test mode
adc.set_test_mode(r, 0)
adc.set_test_mode(r, 1)
adc.sync_adc(r,zdok_0=True,zdok_1=False)

BITS = 8
DELAY_RANGE = 32
CORES = 4
glitches = np.zeros([CORES,BITS,DELAY_RANGE])
for delay in range(DELAY_RANGE):
    print "setting delay %d"%(delay)
    set_io_delay(r,0,0,delay)
    set_io_delay(r,0,1,delay)
    set_io_delay(r,0,2,delay)
    set_io_delay(r,0,3,delay)
    test_vec = np.array(adc.get_test_vector(r, ['snapshot_adc0']))
    #for i in range(4096):
    #    print np.binary_repr(core_a[i],width=8),
    #    print np.binary_repr(core_b[i],width=8),
    #    print np.binary_repr(core_c[i],width=8),
    #    print np.binary_repr(core_d[i],width=8)
    #    print core_a[i],
    #    print core_b[i],
    #    print core_c[i],
    #    print core_d[i]
    for core in range(CORES):
        for bit in range(BITS):
            glitches[core,bit,delay] = glitches_by_bit(test_vec[core],bit)

for core in range(CORES):
    print "##### GLITCHES FOR CORE %d BY IODELAY #####"%core
    for delay in range(DELAY_RANGE):
        print "%2d:"%delay,
        for bit in range(BITS):
            print "%4d"%glitches[core,bit,delay],
        print "TOTAL %d"%glitches.sum(axis=1)[core,delay]


#select_best_delay(glitches)
#
#
set_io_delay(r,0,0,6,bit=0)
set_io_delay(r,0,0,6,bit=1)
set_io_delay(r,0,0,6,bit=2)
set_io_delay(r,0,0,6,bit=3)
set_io_delay(r,0,0,7,bit=4)
set_io_delay(r,0,0,6,bit=5)
set_io_delay(r,0,0,6,bit=6)
set_io_delay(r,0,0,6,bit=7)


set_io_delay(r,0,1,6,bit=0)
set_io_delay(r,0,1,5,bit=1)
set_io_delay(r,0,1,5,bit=2)
set_io_delay(r,0,1,4,bit=3)
set_io_delay(r,0,1,6,bit=4)
set_io_delay(r,0,1,5,bit=5)
set_io_delay(r,0,1,6,bit=6)
set_io_delay(r,0,1,4,bit=7)

set_io_delay(r,0,2,6,bit=0)
set_io_delay(r,0,2,5,bit=1)
set_io_delay(r,0,2,5,bit=2)
set_io_delay(r,0,2,4,bit=3)
set_io_delay(r,0,2,4,bit=4)
set_io_delay(r,0,2,6,bit=5)
set_io_delay(r,0,2,4,bit=6)
set_io_delay(r,0,2,5,bit=7)

set_io_delay(r,0,3,5,bit=0)
set_io_delay(r,0,3,3,bit=1)
set_io_delay(r,0,3,3,bit=2)
set_io_delay(r,0,3,3,bit=3)
set_io_delay(r,0,3,3,bit=4)
set_io_delay(r,0,3,4,bit=5)
set_io_delay(r,0,3,3,bit=6)
set_io_delay(r,0,3,4,bit=7)
#set_io_delay(r,0,0,13)#14)
#set_io_delay(r,0,1,13)#14)
#set_io_delay(r,0,2,13)#2)
#set_io_delay(r,0,3,10)#10)
#core_a, core_c, core_b, core_d = adc.get_test_vector(r, ['snapshot_adc0'])
#print "core A glitches:", adc.total_glitches(core_a, 8)
#print "core B glitches:", adc.total_glitches(core_b, 8)
#print "core C glitches:", adc.total_glitches(core_c, 8)
#print "core D glitches:", adc.total_glitches(core_d, 8)


adc.set_spi_register(r,0,0x05+0x80,0) #use counter test mode
adc.set_test_mode(r, 0)
adc.set_test_mode(r, 1)
adc.sync_adc(r,zdok_0=True,zdok_1=False)

#opt0, glitches0 = adc.calibrate_mmcm_phase(r, 0, ['snapshot_adc0',])
#print "CHOSEN PHASE SHIFT INDEX:",opt0
##opt1, glitches1 = adc.calibrate_mmcm_phase(r, 1, ['snapshot_adc1',])
#adc.unset_test_mode(r, 0)
#adc.unset_test_mode(r, 1)
