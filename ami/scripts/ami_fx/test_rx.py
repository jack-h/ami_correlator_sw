import socket, numpy as np, struct
import time
import ami.ami as AMI
import pylab

IP = '10.1.1.1'
PORT = 10000
words_per_pkt = 55*2
PKT_SIZE = words_per_pkt*4 + 8 + 4 + 4
pkt_fmt = '>qii%di'%words_per_pkt
bufsize = 1024*1024*8

expected_pkt = tuple([i*1024 for i in range(words_per_pkt)])

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, bufsize)

s.bind((IP,PORT))

corr = AMI.AmiSbl(config_file=None, passive=True)
chan_map = np.zeros([corr.n_xengs * (corr.n_chans*corr.n_bands / corr.n_xengs)], dtype=int)
for xn in range(corr.n_xengs):
    chan_map[xn * 408 : (xn+1) * 408] = corr.redis_host.get('XENG%d_CHANNEL_MAP'%xn)[:]


#for xn in range(corr.n_xengs):
#    for i, chan in enumerate(chan_map[xn]):
#        print 'xeng %d, index %d, chan %d'%(xn, i, chan)


n_bls = 10/2*11
n_bytes_per_chan = n_bls * 2 * 4
n_bytes_per_int = corr.n_bands * 2048 * n_bytes_per_chan
datbuf = np.ones([4, corr.n_bands * 2048, n_bls*2], dtype=np.int32) * -1
print 'creating buffer of %d bytes'%(4*n_bytes_per_int)
datbuf_ba = bytearray(4 * n_bytes_per_int)
buffers = []
for i in range(4):
    buffers += [buffer(datbuf_ba, i*n_bytes_per_int, n_bytes_per_int)]
xeng_buf = np.zeros([4, 4096])
xeng_offset_buf = np.zeros([4,4096])
datctr= np.zeros(4)

i = 0
j = 0
last_int = 0
buf_id = 0
while True:
   try:
       data, addr = s.recvfrom(PKT_SIZE)
       #print i, 'received from %s:%d'%addr
       d = struct.unpack('>qll', data[0:16])
       #d = struct.unpack(pkt_fmt, data)
       mcnt = d[0]
       xeng = d[1]
       offset = d[2]
       #bldata = d[3:]
       #buf_id = (mcnt >> 22) % 4
       buf_loc = chan_map[xeng*408 + offset]
       #bldata = data[16:]
       #packet_ok = d[3:]==expected_pkt
       if (offset == 0):# or (offset == 100):
           if j % 10 == 0:
               old_buf = (buf_id + 2) % 4
               print 'Packets in buffer %d: %d'%(old_buf, datctr[old_buf])
               datctr[old_buf] = 0
               buf_id = (buf_id + 1) % 4
               this_int = time.time()
               print '############# New integration after %.2f seconds'%(this_int - last_int)
               last_int = time.time()
           #print 'mcnt: %d (%d) (Buffer: %d), xeng: %d (%s), offset: %d'%(mcnt, mcnt>>(12), buf_id, xeng, addr[0], offset)
           j += 1
       #print 'xeng, offset, chan, datalen:', xeng, offset, chan_map[xeng, offset], len(bldata) 
       #datbuf[(d[0] >> (24)) % 4, chan_map[xeng, offset]] = bldata
       #datbuf[buf_id, buf_loc] = bldata
       datbuf[buf_id, buf_loc] = np.fromstring(data[16:], dtype='>i')
       
       #print (buf_id * n_bytes_per_int) + (buf_loc * n_bytes_per_chan)
       #datbuf_ba[(buf_id * n_bytes_per_int) + (buf_loc * n_bytes_per_chan) : (buf_id * n_bytes_per_int) + ((buf_loc+1) * n_bytes_per_chan)] = data[16:]

       #xeng_offset_buf[buf_id, buf_loc] = offset
       #xeng_buf[buf_id, buf_loc] = xeng
       datctr[buf_id] += 1
       #if not packet_ok:
       #    print d[3:]
       #i += 1
       
   except KeyboardInterrupt:
       s.close()
       #pylab.figure()
       #for chan in range(4096):
       #    pylab.plot(datbuf[1,chan,:], label='%d'%chan)

       pylab.figure()
       pylab.plot(np.sqrt(datbuf[1,:,8]//(1024*1024)))
       pylab.plot(np.sqrt(datbuf[1,:,9]//(1024*1024)))
       for chan in range(4096):
           print 'Chan %d: %d + %dj (Xeng %d, id %d)'%(chan, datbuf[1,chan,9]//(1024*1024), datbuf[1,chan,8]//(1024*1024), xeng_buf[1,chan], xeng_offset_buf[1,chan])
       pylab.show()
