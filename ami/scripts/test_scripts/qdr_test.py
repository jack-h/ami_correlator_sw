import numpy as np
import corr
import time
import struct
import pylab

ROACH = 'bob'

print 'Connecting to %s'%ROACH
r = corr.katcp_wrapper.FpgaClient(ROACH)
time.sleep(0.1)

BOFFILE='qdr_test.bof'
print 'Programming with %s'%BOFFILE
r.progdev(BOFFILE)
time.sleep(0.5)
print 'Board Clock'
print r.est_brd_clk()

print 'phy up?', r.read_int('phy_ready')
print 'cal fail?', r.read_int('cal_fail')


print 'Triggering reset'
r.write_int('rst',0)
r.write_int('rst',1)

#The firmware delays the reset by 1s, so arm the snapshot and wait for data
print 'Arming snap'
s = r.snapshot_get('snapshot_data',wait_period=2, man_valid=True)
d = struct.unpack('>%dQ'%(s['length']/8),s['data'])

d=np.array(d)

data = d[1::2] & (2**7 - 1)
valid = d[0::2] & 1
ack = (d[0::2] & 2) >> 1

#pylab.subplot(3,1,1)
pylab.plot(data)
#pylab.ylabel('data')
#pylab.subplot(3,1,2)
pylab.plot(valid*128)
#pylab.ylabel('valid')
#pylab.subplot(3,1,3)
pylab.plot(ack*64)
#pylab.ylabel('ack')

PRINTRANGE=60
print 'valid, ack, data'
for i in range(PRINTRANGE):
    print '%d %d %d'%(valid[i],ack[i],data[i])

pylab.show()
