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
    p.set_description(__doc__)
    p.add_option('-p', '--skip_prog', dest='skip_prog',action='store_true', default=False, 
        help='Skip FPGA programming (assumes already programmed).  Default: program the FPGAs')
    p.add_option('-l', '--passive', dest='passive',action='store_true', default=False, 
        help='Use this flag to connect to the roaches without reconfiguring them')
    p.add_option('-s', '--set_phase_switch', dest='phase_switch', type='int', default=-1, 
        help='override the phase switch settings from the config file with this boolean value. 1 for enable, 0 for disable.')
    p.add_option('-d', '--debug_chan', dest='debug_chan', type='str', default=None, 
        help='Hack the roach arp tables so that a "chan,IP,mac" set are used. Comma separated, no spaces. Chan=int, IP=str, mac=hex int.')
    p.add_option('-a', '--skip_arm', dest='skip_arm',action='store_true', default=False, 
        help='Use this switch to disable sync arm')
    p.add_option('--cttvg', dest='cttvg',action='store_true', default=False, 
        help='Use corner turn tvg. Default:False')
    p.add_option('--adctvg', dest='adctvg',action='store_true', default=False, 
        help='Use ADC noise generator tvgs. Default:False')
    p.add_option('-m', '--manual_sync', dest='manual_sync',action='store_true', default=False, 
        help='Use this flag to issue a manual sync (useful when no PPS is connected). Default: Do not issue sync')
    p.add_option('-P', '--plot', dest='plot',action='store_true', default=False, 
        help='Plot adc and spectra values')

    opts, args = p.parse_args(sys.argv[1:])

    if args == []:
        config_file = None
    else:
        config_file = args[0]

    # construct the correlator object, which will parse the config file and try and connect to
    # the roaches
    # If passive is True, the connections will be made without modifying
    # control software. Otherwise, the connections will be made, the roaches will be programmed and control software will be reset to 0.
    corr = AMI.AmiDC(config_file=config_file, passive=opts.passive, skip_prog=opts.skip_prog)
    time.sleep(0.1)

    COARSE_DELAY = 64
    corr.set_walsh()
    if opts.phase_switch == -1:
        #don't override
        corr.set_phase_switches(override=None)
    else:
        corr.set_phase_switches(override=bool(opts.phase_switch))

    corr.all_fengs('set_fft_shift',corr.c_correlator['fft_shift'])
    corr.all_fengs('set_coarse_delay',COARSE_DELAY)

    #corr.fengs[0].set_coarse_delay(COARSE_DELAY)
    #corr.fengs[1].set_coarse_delay(COARSE_DELAY+100)
    corr.all_fengs('tvg_en', corner_turn=opts.cttvg, adc=opts.adctvg)
    corr.all_xengs('set_acc_len')
    if not opts.skip_arm:
        corr.disable_tge_output()
        corr.arm_sync(send_sync=opts.manual_sync)
        time.sleep(3)
        corr.enable_tge_output()

    #Enable outputs
    if not opts.passive:
        #corr.enable_tge_output()
        #corr.set_chan_dests_half_rate(enable_output=1)
        corr.set_xeng_outputs()

    if opts.debug_chan is not None:
        chan_str, ip_str, mac_str = opts.debug_chan.split(',')
        chan = int(chan_str)
        mac = int(mac_str, 16)
        corr.tap_channel(chan, ip_str, mac)


    # Arm vaccs 10s in the future
    if not opts.skip_arm:
        corr.arm_vaccs(time.time() + 10)

    for xeng in corr.xengs:
        xeng.reset_ctrs()

    # Reset status flags, wait a second and print some status messages
    corr.all_fengs('clr_status')
    time.sleep(2)
    corr.all_fengs('print_status')
    
    if opts.plot:
        # snap some data
        #pylab.figure()
        n_plots = len(corr.fengs)
        #for fn,feng in enumerate(corr.fengs):
        #    adc = feng.snap('snapshot_adc', man_trig=True, format='b', wait_period=1)
        #    pylab.subplot(n_plots,1,fn)
        #    pylab.plot(adc)
        #    pylab.title('ADC values: ROACH %s, ADC %d, (ANT %d, BAND %s)'%(feng.roachhost.host,feng.adc,feng.ant,feng.band))

        pylab.figure()
        for fn,feng in enumerate(corr.fengs):
            spectra = feng.get_spectra()
            pylab.subplot(n_plots,1,fn+1)
            pylab.plot(spectra)
            pylab.title('Spectra: ROACH %s, ADC %d, (ANT %d, BAND %s)'%(feng.roachhost.host,feng.adc,feng.ant,feng.band))

        pylab.figure()
        for fn,feng in enumerate(corr.fengs):
            spectra = np.abs(feng.get_quant_spectra())**2
            pylab.subplot(n_plots,1,fn+1)
            pylab.plot(spectra)
            pylab.title('4-bit spectra: ROACH %s, ADC %d, (ANT %d, BAND %s)'%(feng.roachhost.host,feng.adc,feng.ant,feng.band))

        print 'Plotting data...'
        print 'Plotting data...'
        pylab.show()




