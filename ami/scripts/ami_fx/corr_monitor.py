import sys
import os
import time
import struct
import numpy as np
import pylab
import socket
import ami.ami as AMI
from ami.helpers import uint2int, dbs, add_default_log_handlers
import logging
import Queue
import threading

logger = add_default_log_handlers(logging.getLogger("%s:%s"%(__file__,__name__)))

def get_eq(in_q, out_q):
    while(True):
        feng = in_q.get()
        out_q.put([feng.num, feng.get_async_spectra(autoflip=False)])
        in_q.task_done()

if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('%prog [options] [CONFIG_FILE]')
    p.set_description(__doc__)
    p.add_option('-p', '--plot', dest='plot', type='int', default=0,
        help='Number of grabs to do before showing plots. Default = 0 = do not plot.')
    p.add_option('-e', '--expire', dest='expire', type='int', default=30,
        help='Expiry time of redis keys in seconds. Default = 30. 0 = do not expire')
    p.add_option('-m', '--monitor', dest='monitor', action='store_true', default=False,
        help='Monitor continuously')
    p.add_option('-n', '--nonoise', dest='noise', action='store_false', default=True,
        help='Use this flag to disable noise switching')

    opts, args = p.parse_args(sys.argv[1:])
    if args == []:
        config_file = None
    else:
        config_file = args[0]

    if opts.expire == 0:
        expire_time = None
    else:
        expire_time = opts.expire

    # initialise connection to correlator
    corr = AMI.AmiDC(config_file=config_file, passive=True, skip_prog=True)
    time.sleep(0.1)

    # redis counters for status
    corr.redis_host.set('corr_monitor:auto_spectra_overrun', 0)
    corr.redis_host.set('corr_monitor:auto_spectra_missing', 0)

    # enable the autocorr capture logic
    logger.info('Turning on auto spectra capturer')
    a = corr.all_fengs('set_auto_capture', True)


    # turn on the noise switch
    logger.info('Setting noise switch enable to %r'%opts.noise)
    a = corr.all_fengs('noise_switch_enable', opts.noise)

    grab_n = 0
    logger.info('Grabbing a dummy spectra for array sizing')
    x = np.zeros_like(corr.all_fengs_multithread('get_spectra', autoflip=False, safe=False))
    spectra = np.zeros_like(x)

    # Set up multiple threads
    in_q = Queue.Queue(maxsize=corr.n_fengs)
    out_q = Queue.Queue(maxsize=corr.n_fengs)
    for t in range(corr.n_fengs):
        worker = threading.Thread(target=get_eq, args=(in_q, out_q))
        worker.setDaemon(True)
        worker.start()

    logger.info('Beginning spectra grab loop')
    last_spectra = corr.fengs[-1].wait_for_new_spectra(last_spectra=0) 

    while(True):
        tic = time.time()
        this_spectra = corr.fengs[-1].wait_for_new_spectra(last_spectra=last_spectra) 
        for fn, feng in enumerate(corr.fengs):
            in_q.put(feng)
        in_q.join()
        for fn, feng in enumerate(corr.fengs):
            num, s = out_q.get()
            out_q.task_done()
            spectra[num] = s
        #spectra = corr.all_fengs_multithread('get_async_spectra', autoflip=False)
        this_spectra_check = corr.fengs[-1].read_int('auto_snap_acc_cnt')

        if (this_spectra_check != this_spectra):
            logger.warning('Looks like a spectra changed during read. Expected %d. Check after read of %d'%(this_spectra, this_spectra_check))
            corr.redis_host.hincrby('corr_monitor:auto_spectra_overrun', 'val', 1)
        if ((last_spectra + 1)%256 != this_spectra_check):
            logger.warning('Looks like a spectra was missed. Expected %d. Check after read of %d'%(last_spectra+1, this_spectra_check))
            corr.redis_host.hincrby('corr_monitor:auto_spectra_missing', 'val', 1)
        last_spectra = this_spectra_check

        eq = corr.all_fengs('get_eq', redishost=corr.redis_host, autoflip=False, per_channel=True)
        for fn, feng in enumerate(corr.fengs):
            key = 'STATUS:noise_demod:ANT%d_%s'%(feng.ant, feng.band)
            d = spectra[fn] * np.abs(eq[fn])**2
            corr.redis_host.set(key, d.tolist(), ex=expire_time)
        logger.info('New monitor data sent at time %.2f'%time.time())
        
	corr.report_alive(__file__, sys.argv)
        if opts.plot != 0:
            x += spectra #* np.abs(eq)**2
            grab_n += 1
            if grab_n == opts.plot:
                break

        if (opts.plot == 0) and not opts.monitor:
            break

        toc = time.time()
        logger.info('monitor loop complete at time %.2f in time %.2f:'%(time.time(), toc - tic))

    if opts.plot != 0:
        pylab.figure(0)
        for fn, feng in enumerate(corr.fengs):
            #pylab.subplot(2,2,fn+1)
            pylab.plot(x[fn], label='Ant %d, %s band'%(feng.ant, feng.band))

        pylab.legend()
        pylab.show()
