#! /usr/bin/env python

import corr
import numpy as np
import pylab
import time
import struct

import adc5g.spi
import adc5g.tools
import adc5g.opb


def graycode(n):
    if n==1:
        return np.array([0,1])
    else:
        g = graycode(n-1)
        return np.concatenate((g,g[::-1]+(1<<(n-1))))

gray = graycode(8) #an 8 bit gray encoder

ROACH = '192.168.0.111'
BOFFILE = 'adc5g_snap.bof'
TEST_MODE = 0
gray_encode = TEST_MODE

r = corr.katcp_wrapper.FpgaClient(ROACH)
time.sleep(0.2)
print "ROACH is connected?", r.is_connected()

#r.progdev(BOFFILE)
#time.sleep(0.2)

f = pylab.figure()
#pylab.ion()

#put the adc into test mode
#adc5g.spi.set_spi_register(r,0,0x05+0x80,0)
adc5g.spi.set_spi_control(r,0,test=0,bg=1)
#adc5g.tools.sync_adc(r,zdok_0=True,zdok_1=False)
adc5g.spi.set_spi_control(r,0,test=TEST_MODE,bg=1)
#adc5g.unset_test_mode(r,0)

#sync adc
adc5g.tools.sync_adc(r,zdok_0=True,zdok_1=False)

#for i in range(8):
#    adc5g.opb.inc_mmcm_phase(r,0)

ii=0
while(ii==0):
    d = r.snapshot_get('snapshot_adc0',
                       man_trig=True,
                       man_valid=True,
                       wait_period=0.2)
    
    dbytes = d['length']
    data = d['data']
    
    print "%d values snapped"%dbytes
    
    dint = np.array(struct.unpack('>%db'%dbytes,data))

    if gray_encode:
        dint = gray[dint]

    dint0 = dint[0::4]
    dint1 = dint[1::4]
    dint2 = dint[2::4]
    dint3 = dint[3::4]
    
    f.clear()
    #pylab.plot(dint0[0:128],label='core0')
    #pylab.plot(dint1[0:128],label='core1')
    #pylab.plot(dint2[0:128],label='core2')
    #pylab.plot(dint3[0:128],label='core3')
    #pylab.legend()
    pylab.plot(dint)


    #for n in range(40):
    #    print np.binary_repr(dint0[n],width=8),
    #    print np.binary_repr(dint1[n],width=8),
    #    print np.binary_repr(dint2[n],width=8),
    #    print np.binary_repr(dint3[n],width=8)
    #exit()
    print "plotting: %d"%ii
    pylab.draw()
    ii += 1
    time.sleep(1)

pylab.show()
