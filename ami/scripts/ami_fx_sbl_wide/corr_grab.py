import sys
import time
import numpy as np
import adc5g as adc
import pylab
import socket
import ami.ami as AMI
import ami.helpers as helpers

if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('%prog [options] [CONFIG_FILE]')
    p.set_description(__doc__)

    opts, args = p.parse_args(sys.argv[1:])

    if args == []:
        config_file = None
    else:
        config_file = args[0]

    corr = AMI.AmiDC(config_file=config_file, verbose=True, passive=True)
    time.sleep(0.1)

    # some non-general code to snap from the X-engine

    starttime = time.time()
    fname = '/data/corr_sbl_%s'%starttime
    data00_fh = open(fname+'.dat00','wb')
    data11_fh = open(fname+'.dat11','wb')
    data01_fh = open(fname+'.dat01','wb')
    time_fh = open(fname+'.timedat','wb')
    mcnt_old = 0
    xeng = corr.xengs[0]
    while(True):
        try:
            mcntlsb = xeng.read_uint('mcnt_lsb')
            mcntmsb = xeng.read_uint('mcnt_msb')
            mcnt = (mcntmsb << 32) + mcntlsb
            if mcnt != mcnt_old:
                print 'Got new accumulation with mcnt', mcnt
                mcnt_old = mcnt
                print 'Snapping data...'
                snap00   = xeng.snap('corr00',wait_period=10,format='q').tostring()
                snap11   = xeng.snap('corr11',wait_period=10,format='q').tostring()
                snap01_r = xeng.snap('corr01_r',wait_period=10,format='q')
                snap01_i = xeng.snap('corr01_i',wait_period=10,format='q')
                snap01   = np.array(snap01_r + 1j*snap01_i, dtype=complex).tostring()
                print 'writing to file'
                time_fh.write('%d'%mcnt)
                data00_fh.write(snap00)
                data11_fh.write(snap11)
                data01_fh.write(snap01)
            if time.time() - starttime > 86400:
                print 'Data grabbing max duration exceeded. Closing files and exiting'
                time_fh.close()
                data00_fh.close()
                data11_fh.close()
                data01_fh.close()
                exit()
        except KeyboardInterrupt:
            print 'Received keyboard interrupt. Closing files and exiting'
            timefh.close()
            data00_fh.close()
            data11_fh.close()
            data01_fh.close()
            exit()
        time.sleep(0.1)



