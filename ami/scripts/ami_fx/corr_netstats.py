import sys
import time
import numpy as np
import adc5g as adc
import pylab
import socket
import ami.ami as AMI
import ami.helpers as helpers
import struct

if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('%prog [options] [CONFIG_FILE]')
    p.add_option('-r', '--reset', dest='reset', action='store_true', default=False, 
        help='Reset stats counters before starting printing')
    p.set_description(__doc__)

    opts, args = p.parse_args(sys.argv[1:])

    if args == []:
        config_file = None
    else:
        config_file = args[0]

    # construct the correlator object, which will parse the config file and try and connect to
    # the roaches
    # If passive is True, the connections will be made without modifying
    # control software. Otherwise, the connections will be made, the roaches will be programmed and control software will be reset to 0.
    corr = AMI.AmiDC(config_file=config_file, passive=True, skip_prog=True)
    time.sleep(0.1)


    if opts.reset:
        for xeng in corr.xengs:
            xeng.reset_ctrs()

    stats = {}
    roachhosts = [xeng.roachhost for xeng in corr.xengs]
    packets_per_spectra = corr.xengs[0].n_chans
    print roachhosts
    while (True):
        #for port in range(4):
        #    stats['lb errors'] = corr.do_for_all('read_uint', roachhosts, 'network_stats%s_lb_err_ctr'%port)
        #    #stats['lb packet errs'] = corr.do_for_all('read_uint', corr.xengs, 'network_stats%s_lb_pkt_err_ctr'%port)
        #    #stats['lb order errs'] = corr.do_for_all('read_uint', corr.xengs, 'network_stats%s_lb_order_err_ctr'%port)
        #    #stats['tge errors'] = corr.do_for_all('read_uint', corr.xengs, 'network_stats%s_tge_err_ctr'%port)
        #    #stats['tge packet errs'] = corr.do_for_all('read_uint', corr.xengs, 'network_stats%s_tge_pkt_err_ctr'%port)
        #    #stats['tge order errs'] = corr.do_for_all('read_uint', corr.xengs, 'network_stats%s_tge_order_err_ctr'%port)
        #    #stats['both errors'] = corr.do_for_all('read_uint', corr.xengs, 'network_stats%s_both_err_ctr'%port)
        #    #stats['last bad lb addr'] = [i // (64*16) for i in corr.do_for_all('read_uint', corr.xengs, 'network_stats%s_last_lb_bad_addr'%port)]
        #    #stats['last bad tge addr'] = [(i // 64) & 0xf for i in corr.do_for_all('read_uint', corr.xengs, 'network_stats%s_last_tge_bad_addr'%port)]
        #    #stats['output eofs'] = corr.do_for_all('read_uint', corr.xengs, 'xeng0_gbe_eof_cnt')
        #    #stats['incomplete spectra'] = [stats['output eofs'][i] % 408 for i in range(corr.n_xengs)]
        for xeng in corr.xengs:
            for port in range(4):
                stats['lb errors'] = xeng.roachhost.read_uint('network_stats%s_lb_err_ctr'%port)
                stats['lb packet errs'] = xeng.roachhost.read_uint('network_stats%s_lb_pkt_err_ctr'%port)
                stats['lb order errs'] = xeng.roachhost.read_uint('network_stats%s_lb_order_err_ctr'%port)
                stats['tge errors'] = xeng.roachhost.read_uint('network_stats%s_tge_err_ctr'%port)
                stats['tge packet errs'] = xeng.roachhost.read_uint('network_stats%s_tge_pkt_err_ctr'%port)
                stats['tge order errs'] = xeng.roachhost.read_uint('network_stats%s_tge_order_err_ctr'%port)
                stats['both errors'] = xeng.roachhost.read_uint('network_stats%s_both_err_ctr'%port)
                stats['last bad lb addr'] = (xeng.roachhost.read_uint('network_stats%s_last_lb_bad_addr'%port) // (64*16)) 
                stats['last bad tge addr'] = (xeng.roachhost.read_uint('network_stats%s_last_tge_bad_addr'%port) //64) & 0xf
                stats['output eofs'] = (xeng.roachhost.read_uint('xeng0_gbe_eof_cnt'))
                stats['incomplete spectra'] = stats['output eofs'] % packets_per_spectra
                print '(%10s) X%dP%d'%(xeng.host, xeng.band, port),
                for name, val in stats.iteritems():
                    print '%s: %3d'%(name,val),
                print ''
        time.sleep(1)
        print '###################################################################################'
            




