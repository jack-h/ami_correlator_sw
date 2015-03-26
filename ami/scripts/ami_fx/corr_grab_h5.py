import sys
import time
import numpy as np
import adc5g as adc
import pylab
import socket
import ami.ami as AMI
import ami.helpers as helpers
import ami.amisa_control as control
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

def write_data(writer, d, timestamp, meta, **kwargs):
    if meta is not None:
        for key, val in meta.iteritems():
           try:
               length = len(val)
               data_type = type(val[0])
           except TypeError:
               length = 1
               data_type = type(val)
           writer.append_data(key, [length], val, data_type)
    writer.append_data('xeng_raw0', d.shape, d, np.int32)
    writer.append_data('timestamp0', [1], timestamp, np.int64)
    for key, value in kwargs.iteritems():
        writer.append_data(key, value.shape, value, value.dtype)

def get_meta_keys(redis_host):
    sampled_meta_keys = []
    file_meta_keys = []
    for key in redis_host.keys():
        ks = key.split(':')
        if (ks[0] == "CONTROL") and (ks[-1] != "last_update_time"):
            if len(ks) > 2:
                file_meta_keys += [key.lstrip('CONTROL:')]
            else:
                sampled_meta_keys += [key.lstrip('CONTROL:')]
    return file_meta_keys, sampled_meta_keys

def get_meta(redis_host, keys):
    extkeys = []
    for k in keys:
        extkeys += ['CONTROL:'+k]
    jsonvals = redis_host.mget(extkeys)
    ret_dict = {}
    for kn, key in enumerate(keys):
        ret_dict[key] = json.loads(jsonvals[kn])
    return ret_dict
    

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



    # get the mapping from xeng_id, chan_index -> total channel number
    corr_chans = corr.n_chans * corr.n_bands
    chans_per_xeng = corr_chans / corr.n_xengs
    chan_map = np.zeros(corr_chans, dtype=int)
    for xn in range(corr.n_xengs):
        chan_map[xn * chans_per_xeng: (xn+1) * chans_per_xeng] = corr.redis_host.get('XENG%d_CHANNEL_MAP'%xn)[:]

    # get the list of meta data names from redis
    file_mk, samp_mk = get_meta_keys(corr.redis_host)
    meta = None #Default value before the receive loop updates the meta data

    # Packet buffers
    N_WINDOWS = 4
    header_fmt = '>qll'
    header_size = struct.calcsize(header_fmt)
    pkt_size = struct.calcsize('%d%s'%(2*corr.n_bls, corr.config['Configuration']['correlator']['hardcoded']['output_format'])) + header_size
    datbuf = np.ones([N_WINDOWS, corr.n_bands * 2048, corr.n_bls*2], dtype=np.int32) * -1
    tsbuf = np.ones(N_WINDOWS, dtype=float) * -1
    datctr= np.zeros(N_WINDOWS)
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
    receiver_enable = False
    last_recv_rst = time.time()
    while True:
        data= s.recv(pkt_size)
        mcnt, xeng, offset = struct.unpack('>qll', data[0:header_size])
        buf_loc = offset#chan_map[xeng*chans_per_xeng + offset]
        #print mcnt, mcnt //4096, mcnt % 4096, xeng, offset
        buf_id = (mcnt // (corr.fengs[0].n_chans * corr.n_bands) // acc_len) % N_WINDOWS
	last_timestamp = tsbuf[buf_id]
	tsbuf[buf_id] = m2t['offset'] + m2t['conv_factor']*(mcnt // 4096)*4096
        #if xeng==0 and offset==0:
        #    print mcnt, buf_id, last_timestamp
        if xeng*2 != (mcnt % 4096):
            logger.error('(check 1) timestamp desync on xeng %d, (2xXENG=%d, mod(mcnt,4096) = %d)'%(xeng, xeng*2, mcnt%4096))

        if (buf_id != last_buf_id):
            sys.stdout.flush()
            if not opts.nometa:
                # Before we deal with the new accumulation, get the current metadata
                meta_buf[buf_id] = get_meta(corr.redis_host, samp_mk)
                file_meta = get_meta(corr.redis_host, file_mk)
                receiver_enable = (meta_buf[buf_id]['obs_status']==4)
                if not receiver_enable:
                    current_obs = None
                    writer.close_file()
                elif file_meta['obs_def:name'] != current_obs:
                    writer.close_file()
                    # fname = 'corr_%s_%d.h5'%(file_meta['obs_def:file'], meta_buf[buf_id]['timestamp'])
                    fname = '%s.h5'%(file_meta['obs_def:file'])
                    if not opts.test_tx:
                        logger.info("Starting a new file with name %s"%fname)
                        writer.start_new_file(fname)
                        for key, val in file_meta.iteritems():
                            writer.add_attr(key, val)
                    current_obs = file_meta['obs_def:name']
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
            if receiver_enable or opts.nometa:
                # When the buffer ID changes, ship the window 1/2 a circ. buffer behind
                if datctr[win_to_ship] == corr_chans:
                    #logger.info('# New integration is complete after %.2f seconds (mcnt offset %.2f) #'%(this_int - last_int, tsbuf[win_to_ship] - tsbuf[(win_to_ship-1)%N_WINDOWS]))
                    datavec = np.reshape(datbuf[win_to_ship], [corr.n_bands * 2048, corr.n_bls, 1, 2]) #chans * bls * pols * r/i
                    # Write integration
                    phased_to = np.array([corr.array.get_sidereal_time(tsbuf[win_to_ship]), corr.array.lat_r])
                    write_data(writer,datavec,tsbuf[win_to_ship], meta_buf[win_to_ship], noise_demod=corr.noise_switched_from_redis(), phased_to=phased_to)
                    # Write to redis
                    redis.Redis.set(corr.redis_host, 'RECEIVER:xeng_raw0', datavec[:].tostring())
                    corr.redis_host.set('RECEIVER:timestamp0', tsbuf[win_to_ship])
                else:
                    logger.error('Packets in buffer %d: %d ####'%(win_to_ship, datctr[win_to_ship]))
            last_buf_id = buf_id
            datctr[win_to_ship] = 0
            last_int = this_int
            if not receiver_enable:
                logger.info('Got an integration but receiver is not enabled')
                #time.sleep(1)
                 
        else:
            if tsbuf[buf_id] != last_timestamp:
                if time.time() > (last_recv_rst + 5): #don't allow a reset until at least 5s after the last
                    logger.error('(check 2) -- timestamp desync! This timestamp (xeng %d) is %.5f, last one was %.5f'%(xeng, tsbuf[buf_id], last_timestamp))
                    logger.info('Rearming vaccs!')
                    corr.arm_vaccs(time.time() + 5)
                    [xeng.reset_gbe() for xeng in corr.xengs]
                    last_recv_rst = time.time()


        datbuf[buf_id, buf_loc] = np.fromstring(data[header_size:], dtype='>i')
        datctr[buf_id] += 1
