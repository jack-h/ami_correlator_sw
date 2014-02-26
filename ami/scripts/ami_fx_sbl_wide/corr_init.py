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
    p.add_option('-p', '--skip_prog', dest='skip_prog',action='store_true', default=False, 
        help='Skip FPGA programming (assumes already programmed).  Default: program the FPGAs')
    p.add_option('-s', '--skip_phase_switch', dest='phase_switch',action='store_false', default=True, 
        help='Use this switch to disable phase switching')
    p.add_option('-a', '--skip_arm', dest='skip_arm',action='store_true', default=False, 
        help='Use this switch to disable sync arm')
    p.add_option('-l', '--passive', dest='passive',action='store_true', default=False, 
        help='Use this flag to connect to the roaches without reconfiguring them')
    p.add_option('-v', '--verbosity', dest='verbosity',type='int', default=0, 
        help='Verbosity level. Default: 0')
    p.add_option('-t', '--tvg', dest='tvg',action='store_true', default=False, 
        help='Use corner turn tvg. Default:False')
    p.add_option('-m', '--manual_sync', dest='manual_sync',action='store_true', default=False, 
        help='Use this flag to issue a manual sync (useful when no PPS is connected). Default: Do not issue sync')
    p.add_option('-n', '--network', dest='network',action='store_true', default=False, 
        help='Send data out over tcp')

    opts, args = p.parse_args(sys.argv[1:])

    if args == []:
        config_file = None
    else:
        config_file = args[0]

    # construct the correlator object, which will parse the config file and try and connect to
    # the roaches
    # If passive is True, the connections will be made without modifying
    # control software. Otherwise, the connections will be made, the roaches will be programmed and control software will be reset to 0.
    corr = AMI.AmiDC(config_file=config_file, verbose=True, passive=opts.skip_prog)
    time.sleep(0.1)

    COARSE_DELAY = 0
    corr.all_fengs('phase_switch_enable',opts.phase_switch)
    corr.all_fengs('set_fft_shift',corr.c_correlator.getint('fft_shift'))
    #corr.all_fengs('set_coarse_delay',COARSE_DELAY)

    corr.fengs[0].set_coarse_delay(COARSE_DELAY)
    corr.fengs[1].set_coarse_delay(COARSE_DELAY)
    corr.all_fengs('tvg_en',corner_turn=opts.tvg)
    corr.all_xengs('set_acc_len')
    if not opts.skip_arm:
        print "Arming sync generators"
        corr.all_fengs('arm_trigger')

    if opts.manual_sync:
        # Trigger data capture
        for feng in corr.fengs:
            # do two, as the first is flushed
            feng.man_sync()
            feng.man_sync()


    # Reset status flags, wait a second and print some status messages
    corr.all_fengs('clr_status')
    time.sleep(1)
    corr.all_fengs('print_status')
    
    if opts.network:
        #set up the socket
        TCP_IP = '127.0.0.1'
        TCP_PORT = 10000
        BUFFER_SIZE = 1024
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((TCP_IP,TCP_PORT))

    # snap some data
    pylab.figure()
    n_plots = len(corr.fengs)
    for fn,feng in enumerate(corr.fengs):
        adc = feng.snap('snapshot_adc', man_trig=True, format='b')
        pylab.subplot(n_plots,1,fn)
        pylab.plot(adc)

    # some non-general code to snap from the X-engine
    print 'Snapping data...'
    xeng = corr.xengs[0]
    snap00   = xeng.snap('corr00',wait_period=10,format='q')
    snap11   = xeng.snap('corr11',wait_period=10,format='q')
    snap01_r = xeng.snap('corr01_r',wait_period=10,format='q')
    snap01_i = xeng.snap('corr01_i',wait_period=10,format='q')
    snap01   = np.array(snap01_r + 1j*snap01_i, dtype=complex)
    



    if opts.network:
        s.send(corr_str)
        s.close()

    pylab.figure()
    pylab.subplot(4,1,1)
    pylab.plot(corr.fengs[0].gen_freq_scale(),helpers.dbs(snap00))
    pylab.subplot(4,1,2)
    pylab.plot(corr.fengs[0].gen_freq_scale(),helpers.dbs(snap11))
    pylab.subplot(4,1,3)
    pylab.plot(corr.fengs[0].gen_freq_scale(),helpers.dbs(np.abs(snap01)))
    pylab.subplot(4,1,4)
    pylab.plot(corr.fengs[0].gen_freq_scale(),np.unwrap(np.angle(snap01)))
    pylab.show()




