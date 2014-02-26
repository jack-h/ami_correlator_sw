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
        #print np.binary_repr(r.read_int(regname,offset=6))

def glitches_by_bit(d,bit):
    SPACING = 11
    glitches = 0
    data = (np.array(d) & (1<<bit))>>bit
    last_index = None
    for i in range(len(d)-SPACING):
        if i%SPACING==0:
            if data[i:i+SPACING].sum() != 1:
                glitches += 1
        if data[i]==1:
            if (last_index is not None) and ((i-last_index) != SPACING):
                glitches += 1
            last_index = i
    return glitches

def find_best_delay(d,clk=625.,ref_clk=200.,verbose=False,offset=0,tolerance=None):
    '''
    A method to set the best bitwise delays for an input data bus. We assume that all the inputs
    are approximately aligned to begin with. I.e. if the input bus is 8 bits, we assume that the relative delays
    of each bit are << 1 clock cycle.
    Arguments:
        d        : An [N_BITS x N_DELAY_TRIALS] array containing numbers of glitches per bit per delay trial.
        clk      : The data transfer clock in any unit (we assume the data rate is DDR and thus double the clk rate)
        ref_clk  : The FPGA IODELAY reference clock, in the same units as clk.
        verbose  : Boolean value. Set to true to print information about what's going on
        offset   : Set to an integer value to skip <offset> stable eyes. This can be used to synchronize multiple interfaces
                   which are whole cycles offset.
        tolerance: Tolerance sets (indirectly) the minimum delay which we consider to be a valid place to look for an eye.
                   This is to accomodate variation of delays of different bits. I.e., if the start of the eye of bit 0 is found at tap 1,
                   the start of the eye of bit 1 may occur at a lower delay than the IODELAY block can provide. The value of <tolerance> should
                   reflect the maximum variation of delays you expect, in units of IODELAY taps. By default it is assumed that
                   all bits are grouped within half an eye (i.e. clk/4 for DDR). If you have trouble calibrating because the delay range
                   is being exhausted (particularly if you are using non-zero offset), you can try and reduce this value to start
                   searching for an eye closer to the minimum tap delay.


        1. Find the first non-zero value more than <tolerance> taps from the start
        2. Find the first zero following this. This marks the start of the eye we want to capture on
        3. Find the next non-zero value. This marks the end of the capture eye.
        4. Set the delay to mid way between these points. Where the midway is not an integer, use the relative number of glitches
           on each side of the eye to determine the most favourable position.
        5. Repeat for the next bit, but begin searching for the first non-zero value one clock cycle earlier than the eye centre
           we have already found.
    '''
    n_bits, n_taps = d.shape
    tap_delay = 1./ref_clk/float(n_taps)/2. #78ps for 200 MHz reference
    if verbose: print "tap_delay: %.1f ps"%(tap_delay*1e6)
    taps_per_cycle = (1./clk)/tap_delay/2. #This gives the number of taps in a complete clock cycle (1/2 because data is DDR)
    if verbose: print "taps_per_cycle: %.1f"%taps_per_cycle
    if tolerance is None:
        search_start_point = int(taps_per_cycle*(offset + 0.5))
    else:
        search_start_point = int(taps_per_cycle*offset + tolerance)
    eye_centres = np.zeros(n_bits,dtype=int)
    for bit in range(n_bits):
        if verbose: print "Starting search for bit %d eye at tap %d"%(bit,search_start_point)
        for delay in range(search_start_point,n_taps):
            if d[bit,delay] != 0:
                #we have found the glitchy area we were looking for
                #this is where we will start our search for the start of the eye
                first_glitch = delay
                if verbose: print "  found first glitch at %d"%first_glitch
                break
            if (d[bit,delay] == 0) and (delay==(n_taps-1)):
                raise Exception("Couldn't find first glitch")
        for delay in range(first_glitch,n_taps):
            if np.all(d[bit,delay:delay+3] == 0): #Check for runs of 3 zeros (sometimes even outside the eye there will be a delay with no glitches)
                #we have found the start of the eye
                eye_start = delay
                if verbose: print "  found eye start at %d"%eye_start
                #record the glitches one tap earlier to help decide which of the
                #two best taps to use if the number of "good" delays is even
                glitches_before_eye = d[bit,delay-1]
                if verbose: print "    glitches before eye: %d"%glitches_before_eye
                break
            if (d[bit,delay] != 0) and (delay==(n_taps-4)):
                raise Exception("Couldn't find start of eye")
        for delay in range(eye_start,n_taps):
            if d[bit,delay] != 0:
                #we have found the end of the eye
                eye_end = delay-1
                if verbose: print "  found eye end at %d"%eye_end
                #record the glitches one tap after the eye closes to help decide which of the
                #two best taps to use if the number of "good" delays is even
                glitches_after_eye = d[bit,delay]
                if verbose: print "    glitches after eye: %d"%glitches_after_eye
                break
            if (d[bit,delay] == 0) and (delay==(n_taps-1)):
                raise Exception("Couldn't find end of eye")
        # Find the middle of the eye
        eye_centre = eye_start + (eye_end - eye_start)/2.
        if verbose: print "  EYE CENTRE at %.1f"%eye_centre
        # tie break the non integer case
        if eye_centre % 1 != 0:
            if glitches_after_eye >= glitches_before_eye:
                eye_centre = np.floor(eye_centre)
            else:
                eye_centre = np.ceil(eye_centre)
            if verbose: print "    TIEBREAK: EYE CENTRE at %d"%eye_centre
        eye_centres[bit] = int(eye_centre)
        if bit == 0:
            #If this is the first bit, use it to define the reference point about which we search for
            #the eyes of other bits
            search_start_point = eye_centres[0] - int(taps_per_cycle)
            if search_start_point < 0:
                search_start_point = 0
            if verbose: print "  NEW START SEARCH REFERENCE POINT IS %d"%search_start_point
    return eye_centres

def check_core_alignment(r,cores=4):
    adc.set_spi_register(r,0,0x05+0x80,0) #use counter
    adc.set_test_mode(r, 0)
    adc.sync_adc(r,zdok_0=True,zdok_1=True)
    test_vec = np.array(adc.get_test_vector(r, ['snapshot_adc0']))
    #for i in range(1):
    #    for core in range(cores):
    #        print "%3d"%test_vec[core,i],
    #    print ''
    s = test_vec[:,0]
    if np.any(s==255): # Lazy way to make sure we aren't looking at a wrapping section of the counter
        s = test_vec[100]
    offset = np.min(s) - s #these are the relative arrival times. i.e. -1 means arrival is one clock too soon
    return offset




ROACH = '192.168.0.111'

r = corr.katcp_wrapper.FpgaClient(ROACH)
time.sleep(0.1)

adc.set_spi_register(r,0,0x05+0x80,1) #use strobing test mode
adc.set_test_mode(r, 0)
adc.set_test_mode(r, 1)
adc.sync_adc(r,zdok_0=True,zdok_1=True)

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


VERBOSE=False
TOLERANCE = 1
delays = np.zeros([CORES,BITS],dtype=int)
for core in range(CORES):
    delays[core,:] = find_best_delay(glitches[core],verbose=VERBOSE,tolerance=TOLERANCE)

for core in range(CORES):
    print "setting core %d delays"%core, delays[core]
    for bit in range(BITS):
        set_io_delay(r,0,core,delays[core,bit],bit=bit)

print ''
print "checking core alignment"
offsets = check_core_alignment(r)
print "offsets:",offsets

#delays = np.zeros([CORES,BITS],dtype=int)
#for core in range(CORES):
#    delays[core,:] = find_best_delay(glitches[core],verbose=VERBOSE,offset=-offsets[core],tolerance=TOLERANCE)
#
#for core in range(CORES):
#    print "setting core %d delays"%core, delays[core]
#    for bit in range(BITS):
#        set_io_delay(r,0,core,delays[core,bit],bit=bit)


print ''
print "checking core alignment"
offsets = check_core_alignment(r)
print "offsets:",offsets


print "Leaving test mode and sync'ing ADC"
adc.spi.set_spi_control(r,0,test=0)
#adc.sync_adc(r,zdok_0=True,zdok_1=True)
