import sys
import time
import numpy as np
import adc5g as adc
import pylab
import socket
import ami.ami as AMI
import ami.helpers as helpers
import ami.control as control
import ami.file_writer as fw
import pylab
import signal
import logging
import struct
import json
import redis
import h5py

logger = helpers.add_default_log_handlers(logging.getLogger("%s:%s"%(__file__,__name__)))

#type_unicode = h5py.special_dtype(vlen=unicode)

def flatten_dict(d, prefix='', separator=':'):
    rv = {}
    for key, val in d.iteritems():
        if isinstance(val, dict):
            flatten_dict(val, prefix=prefix+key+separator)
        else:
            rv[prefix+key] = val
    return rv

def write_file_attributes(writer, meta):
    for key, val in flatten_dict(meta['tel_def'], prefix='tel_def:').iteritems():
        writer.add_attr(key, val)
    for key, val in flatten_dict(meta['src_def'], prefix='src_def:').iteritems():
        writer.add_attr(key, val)
    for key, val in flatten_dict(meta['obs_def'], prefix='obs_def:').iteritems():
        writer.add_attr(key, val)
            
def write_data(writer, d, timestamp, meta, **kwargs):
    if meta is not None:
        for key, val in meta.iteritems():
           if not isinstance(val, dict):
               # don't write nested dictionaries.
               try:
                   length = len(val)
                   data_type = type(val[0])
               except TypeError:
                   length = 1
                   data_type = type(val)
               writer.append_data(key, [length], val, data_type)
    writer.append_data('xeng_raw0', d.shape, d, np.int32)
    writer.append_data('timestamp0', [1], timestamp, np.float64)
    for key, value in kwargs.iteritems():
        writer.append_data(key, value.shape, value, value.dtype)

def redis_delays_valid(corr, time):
    # time is a timestamp of the centre of an integration. the
    # time in redis is the timestamp of a start of integration
    # 2.01 rather than 2 is a clurge to sidestep precision issues
    if not (time - (corr.acc_time/2.01)) > corr.get_coarse_delay_load_time():
        #print time, time-(corr.acc_time/2.01), corr.get_coarse_delay_load_time(), corr.acc_time
        return False
    else:
        return True

def unwrap_delays(corr, d, delays):
    bw = corr.adc_clk / 2.
    cbw = bw/corr.f_n_chans
    freqs = np.linspace(0, bw - cbw, corr.f_n_chans)
    dual_band_freqs = np.concatenate((freqs, freqs))
    phases = np.zeros([corr.n_ants, corr.n_bands*freqs.shape[0]], dtype=np.complex64)
    dc = np.zeros([dual_band_freqs.shape[0], corr.n_bls], dtype=np.complex64)
    for bln, bl in enumerate(corr.bl_order):
        # DELAYS ARE IN ADC CLOCKS!!
        dc[:, bln] = (d[:, bln, 0, 1] + 1j*d[:, bln, 0, 0]) * np.exp(1j * 2 * np.pi * dual_band_freqs * (delays[bl[0]] - delays[bl[1]]) / corr.adc_clk)
    d[:,:,0,1] = np.array(dc.real, dtype=np.int32)
    d[:,:,0,0] = np.array(dc.imag, dtype=np.int32)

def signal_handler(signum, frame):
    """
    Run when kill signals are caught
    """
    print "Received kill signal %d. Closing files and exiting"%signum
    writer.close_file()
    try:
        ctrl.close_sockets()
    except:
       pass #this is poor form
    exit()


if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('%prog [options] [CONFIG_FILE]')
    p.set_description(__doc__)
    p.add_option('-t', '--test_tx', dest='test_tx',action='store_true', default=False, 
        help='Send tx test patterns, and don\'t bother writing data to file')
    p.add_option('-n', '--nometa', dest='nometa',action='store_true', default=False, 
        help='Use this option to ignore metadata')
    p.add_option('-p', '--phs2src', dest='phs2src',action='store_true', default=False, 
        help='Phase the data to the source indicated by the ra,dec meta data')

    opts, args = p.parse_args(sys.argv[1:])

    if args == []:
        config_file = None
    else:
        config_file = args[0]

    # This initiates connections to the ROACHs, which isn't really necessary
    corr = AMI.AmiDC()
    time.sleep(0.1)

    writer = fw.H5Writer(config_file=config_file)
    writer.set_bl_order(corr.bl_order)

    # Set some status counters
    corr.redis_host.set('corr_grab:n_integrations', 0)
    corr.redis_host.set('corr_grab:n_tge_rearms', 0)
    corr.redis_host.set('corr_grab:n_lost_packets', 0)


    # get the mapping from xeng_id, chan_index -> total channel number
    corr_chans = corr.n_chans * corr.n_bands
    chans_per_xeng = corr_chans / corr.n_xengs
    chan_map = np.zeros(corr_chans, dtype=int)
    for xn in range(corr.n_xengs):
        chan_map[xn * chans_per_xeng: (xn+1) * chans_per_xeng] = corr.redis_host.get('XENG%d_CHANNEL_MAP'%xn)[:]

    meta = None #Default value before the receive loop updates the meta data

    # Packet buffers
    N_WINDOWS = 4
    header_fmt = '>qll'
    header_size = struct.calcsize(header_fmt)
    pkt_size = struct.calcsize('%d%s'%(2*corr.n_bls, corr.config['Configuration']['correlator']['hardcoded']['output_format'])) + header_size
    datbuf = np.ones([N_WINDOWS, corr.n_bands * 2048, corr.n_bls*2], dtype=np.int32) * -1
    tsbuf = np.ones(N_WINDOWS, dtype=float) * -1
    datctr= np.zeros(N_WINDOWS, dtype=np.int32)
    acc_len = corr.config['XEngine']['acc_len']
    meta_buf = [{} for i in range(N_WINDOWS)]

    # Catch keyboard interrupt and kill signals (which are initiated by amisa over ssh)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # preload the mcnt -> time conversion factors.
    # NOTE: this will break if the sync time changes
    m2t = corr.get_mcnt2time_factors()

    # Configure the receiver socket
    BUFSIZE = 1024*1024*8 #This should be a couple of integrations
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, BUFSIZE)
    bufsize_readback = s.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
    if bufsize_readback != 2*BUFSIZE: #2*, is this a bug?
        print 'ERROR: Tried to set a socket buffer of size %d bytes, but readback indicated %d bytes were allocated!'%(BUFSIZE, bufsize_readback)
        exit()
    s.bind((corr.c_correlator['one_gbe']['dest_ip'],corr.c_correlator['one_gbe']['port']))

    # Main network receive loop
    last_buf_id = 0
    last_int = 0
    current_obs = None
    delays = None
    receiver_enable = False
    last_recv_rst = time.time()
    int_cnt = 0
    while True:
        data= s.recv(pkt_size)
        mcnt, xeng, offset = struct.unpack('>qll', data[0:header_size])
        buf_loc = offset#chan_map[xeng*chans_per_xeng + offset]
        #print mcnt, mcnt //4096, mcnt % 4096, xeng, offset
        buf_id = (mcnt // (corr.fengs[0].n_chans * corr.n_bands) // acc_len) % N_WINDOWS
	last_timestamp = tsbuf[buf_id]

        # Convert timestamp to time and subtract off half an integration so it marks the center
	tsbuf[buf_id] = (m2t['offset'] + m2t['conv_factor']*(mcnt // 4096)*4096) - (0.5*corr.acc_time)
        #if xeng==0 and offset==0:
        #    print mcnt, buf_id, last_timestamp
        if xeng*2 != (mcnt % 4096):
            logger.error('(check 1) timestamp desync on xeng %d, (2xXENG=%d, mod(mcnt,4096) = %d)'%(xeng, xeng*2, mcnt%4096))

        if (buf_id != last_buf_id):
	    corr.report_alive(__file__)
            sys.stdout.flush()
            if not opts.nometa:
                # Before we deal with the new accumulation, get the current metadata
                meta_buf[buf_id] = corr.redis_host.get('CONTROL')
                receiver_enable = (meta_buf[buf_id]['obs_status']==4)
                if not receiver_enable:
                    current_obs = None
                    writer.close_file()
                elif meta_buf[buf_id]['obs_def']['name'] != current_obs:
                    writer.close_file()
                    # fname = 'corr_%s_%d.h5'%(file_meta['obs_def:file'], meta_buf[buf_id]['timestamp'])
                    fname = '%s.h5'%(meta_buf[buf_id]['obs_def']['file'])
                    if not opts.test_tx:
                        logger.info("Starting a new file with name %s"%fname)
                        writer.start_new_file(fname)
                        write_file_attributes(writer, meta_buf[buf_id])
                    current_obs = meta_buf[buf_id]['obs_def']['name']
                if time.time() - meta_buf[buf_id]['timestamp'] > 60*10:
                    if receiver_enable:
                        logger.warning("10 minutes has elapsed since last valid meta timestamp. Closing files")
                    #set current obs to none so the next valid obs will trigger a new file
                    current_obs = None
                    writer.close_file()
                    receiver_enable = False # disable data capture until new meta data arrives
            else:
                if current_obs is None:
                    fname = 'corr_TEST_%d.h5'%(time.time())
                    writer.start_new_file(fname)
                    current_obs = 'test'
                    receiver_enable = True

            win_to_ship = (buf_id - (N_WINDOWS // 2)) % N_WINDOWS
	    this_int = time.time()
            logger.info('got window %d after %.4f seconds (mcnt offset %.4f), shipping window %d (time %.5f)'%(buf_id, this_int - last_int, tsbuf[win_to_ship] - tsbuf[(win_to_ship-1)%N_WINDOWS], win_to_ship, tsbuf[win_to_ship]))
            corr.redis_host.hincrby('corr_grab:n_integrations', 'val', 1)
            # When the buffer ID changes, ship the window 1/2 a circ. buffer behind
            if datctr[win_to_ship] == corr_chans:
                int_cnt += 1
                #logger.info('# New integration is complete after %.2f seconds (mcnt offset %.2f) #'%(this_int - last_int, tsbuf[win_to_ship] - tsbuf[(win_to_ship-1)%N_WINDOWS]))
                datavec = np.reshape(datbuf[win_to_ship], [corr.n_bands * 2048, corr.n_bls, 1, 2]) #chans * bls * pols * r/i
                # Write integration
                phased_to = np.array([corr.array.get_sidereal_time(tsbuf[win_to_ship]), corr.array.lat_r])
                # If the accumulation timestamp is later than the coarse delays
                # stored in redis, get the new delays set and use that for phase
                # rotation. Otherwise, keep using the last delay set.
                # This assumes that delays are updated in redis slowly compared to
                # integration time, which should be a safe assumption.
                ##print 'foo', np.array(datavec[200:210,5,0,1], dtype=np.int64)**2 + np.array(datavec[200:210,5,0,0], dtype=np.int64)**2
                if (delays is None) or redis_delays_valid(corr, tsbuf[win_to_ship]):
                    delays = corr.get_coarse_delays()
                else:
                    logger.info('Redis delays newer than data -- not using them this time')
                # rotate the phases of the data array in place
                unwrap_delays(corr, datavec, delays)
                ##print 'bar', np.array(datavec[200:210,5,0,1], dtype=np.int64)**2 + np.array(datavec[200:210,5,0,0], dtype=np.int64)**2

                # Write to redis
                redis.Redis.hmset(corr.redis_host, 'RECEIVER:xeng_raw0', {'val':datavec[:].tostring(), 'timestamp':tsbuf[win_to_ship]})
                if receiver_enable or opts.nometa:
                    write_data(writer,datavec,tsbuf[win_to_ship], meta_buf[win_to_ship], noise_demod=corr.noise_switched_from_redis(), phased_to=phased_to)
                else:
                    logger.info('Got an integration but receiver is not enabled')
            elif int_cnt > N_WINDOWS: #ignore the first empty buffers
                logger.error('Packets in buffer %d: %d ####'%(win_to_ship, datctr[win_to_ship]))
                corr.redis_host.hincrby('corr_grab:n_lost_packets', 'val', corr_chans - datctr[win_to_ship])

            last_buf_id = buf_id
            datctr[win_to_ship] = 0
            last_int = this_int
                 
        else:
            if tsbuf[buf_id] != last_timestamp:
                if time.time() > (last_recv_rst + 5): #don't allow a reset until at least 5s after the last
                    logger.error('(check 2) -- timestamp desync! This timestamp (xeng %d) is %.5f, last one was %.5f'%(xeng, tsbuf[buf_id], last_timestamp))
                    logger.info('Rearming vaccs!')
                    corr.redis_host.hincrby('corr_grab:n_tge_rearms', 'val', 1)
                    corr.arm_vaccs(time.time() + 5)
                    [xeng.reset_gbe() for xeng in corr.xengs]
                    last_recv_rst = time.time()


        datbuf[buf_id, buf_loc] = np.fromstring(data[header_size:], dtype='>i')
        datctr[buf_id] += 1
