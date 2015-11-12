import curses
import curses.wrapper
import time
from ami import config_redis
import os
import yaml
import numpy as np
from corr import sim


def get_free_disk_space(path):
    x = os.statvfs(path)
    return x.f_bavail * x.f_frsize / (1024.**3)

def get_mean_powers(r, c):
    '''
    Get autocorrelation powers from redis
    and scale them appropriately.
    '''
    # find indices of correlation matrices representing autos
    corr_conf = c['Configuration']['correlator']['hardcoded']
    bl_order = sim.get_bl_order(corr_conf['n_ants'])
    n_bls = len(bl_order)
    auto_indices = np.zeros(corr_conf['n_ants'])
    for bn, bl in enumerate(bl_order):
        if bl[0] == bl[1]:
            auto_indices[bl[0]] = bn
    # get current data and store as numpy array
    data, ts = r.hmget('RECEIVER:xeng_raw0', ['val', 'timestamp'])
    n_chans = c['FEngine']['n_chans']
    ts = float(ts)
    data_c = np.fromstring(data, dtype=np.int32).reshape([corr_conf['n_bands'] * n_chans, n_bls, 1, 2])
    # carve out the autos
    autos = np.zeros([corr_conf['n_ants'], corr_conf['n_bands'] * n_chans], dtype=np.float32)
    for an, auto_index in enumerate(auto_indices):
        autos[an] = data_c[:, auto_index, 0, 1] / c['XEngine']['acc_len'] / corr_conf['window_len'] #This is scaled relative to a correlator input between +/-7
    return autos

def get_mean_amps(r, c):
    return np.sqrt(get_mean_powers(r,c)) / np.sqrt(2)
    
    

def get_int_time(config):
    return config['XEngine']['acc_len'] * config['Configuration']['correlator']['hardcoded']['window_len'] / config['FEngine']['adc_clk'] / 1e6 * config['FEngine']['n_chans'] * 2

def check_scripts(r, scripts):
    n_scripts = len(scripts)
    keys = r.keys()
    is_alive = [False] * n_scripts
    paths = [''] * n_scripts
    for sn, script in enumerate(scripts):
        for k in r.keys():
            if k.endswith(script+'_ALIVE'):
                is_alive[sn] = True
                paths[sn] = k.rstrip('_ALIVE')
    return is_alive, paths
        
def display_status(screen, r):

    curses.noecho() #don't show keys pressed
    curses.cbreak() #react to keys instantly rather than waiting for enter
    curses.curs_set(0) # hide the cursor
    screen.nodelay(1)

    # Look like gbtstatus (why not?)
    curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_WHITE, curses.COLOR_RED)
    keycol = curses.color_pair(1)
    valcol = curses.color_pair(2)
    errcol = curses.color_pair(3)


    # scripts to check aliveness
    scripts = ['corr_track_delays.py', 'corr_grab_h5.py', 'corr_monitor.py', 'corr_ctrl_redis_bridge.py']
    

    last_config_update_time = 0
    while(True):
        
        screen.erase()
        screen.border(0)
        (ymax, xmax) = screen.getmaxyx()

        curline = 4
        col = 5
        # Configuration information
        config_update_time = float(r.hget('config', 'unixtime'))
        if config_update_time != last_config_update_time:
            host = r.hget('config', 'host')
            fn = r.hget('config', 'file')
            config_file = '%s:%s'%(host, fn)
            config = yaml.load(r.hget('config', 'conf'))
        last_config_update_time = config_update_time

        screen.addstr(curline, col, time.ctime())
        curline = min(ymax-1, curline+1)
        screen.addstr(curline, col, 'CONFIGURATION : ', keycol)
        screen.addstr('%s'%config_file, valcol)
        curline = min(ymax-1, curline+1)
        screen.addstr(curline, col, 'UPDATED : ', keycol)
        screen.addstr(time.ctime(config_update_time), valcol)
        curline = min(ymax-1, curline+2)

        # Script alive checks
        is_alive, paths = check_scripts(r, scripts)
        screen.addstr(curline, col, 'SCRIPT STATUS')
        curline = min(ymax-1, curline+2)

        for sn, s in enumerate(scripts):
            if is_alive[sn]:
                screen.addstr(curline, col, s+' is alive ', valcol)
                screen.addstr('(%s)'%paths[sn])
            else:
                screen.addstr(curline, col, s+' is not alive', errcol)
            curline = min(ymax-1, curline+1)

        # Misc correlator stats
        curline = min(ymax-1, curline+1)
        screen.addstr(curline, col, 'CORRELATOR STATS')
        curline = min(ymax-1, curline+2)
        screen.addstr(curline, col, 'LAST CORRELATOR SYNC: ', keycol)
        screen.addstr('%s'%time.ctime(r.get('sync_time')), valcol)
        curline = min(ymax-1, curline+1)
        screen.addstr(curline, col, 'ANTENNA AMPLITUDES :', keycol)
        amps = get_mean_amps(r,config)
        n_ants, n_chans = amps.shape
        for i in range(8):
            start_chan = i*n_chans/8
            stop_chan = (i+1)*n_chans/8
            mean = amps[:,start_chan:stop_chan].mean(axis=1)
            curline = min(ymax-1, curline+1)
            screen.addstr(curline, col, 'CHANS %.4d-%.4d : '%(start_chan, stop_chan), keycol)
            screen.addstr('%s'%np.array_str(mean, precision=3), valcol)

        # Status info
        curline = min(ymax-1, curline+2)
        screen.addstr(curline, col, 'STATUS COUNTERS')
        curline = min(ymax-1, curline+2)
        screen.addstr(curline, col, 'N_INTEGRATIONS : ', keycol)
        screen.addstr('%d'%r.get('corr_grab:n_integrations'), valcol)
        curline = min(ymax-1, curline+1)
        screen.addstr(curline, col, 'N_TGE_ERRS: ', keycol)
        screen.addstr('%d'%r.get('corr_grab:n_tge_rearms'), valcol)
        curline = min(ymax-1, curline+1)
        screen.addstr(curline, col, 'N_LOST_PACKETS: ', keycol)
        screen.addstr('%d'%r.get('corr_grab:n_lost_packets'), valcol)

        curline = min(ymax-1, curline+2)
        screen.addstr(curline, col, 'N_RAIN_GAUGE_MISSING: ', keycol)
        screen.addstr('%d'%r.get('corr_monitor:auto_spectra_missing'), valcol)
        curline = min(ymax-1, curline+1)
        screen.addstr(curline, col, 'N_RAIN_GAUGE_READ_ERRS: ', keycol)
        screen.addstr('%d'%r.get('corr_monitor:auto_spectra_overrun'), valcol)

        curline = min(ymax-1, curline+2)
        screen.addstr(curline, col, 'GEOMETRIC DELAYS (ps): ', keycol)
        screen.addstr('%s'%r.get('CONTROL')['delay'], valcol)
        curline = min(ymax-1, curline+1)
        screen.addstr(curline, col, 'APPLIED DELAYS (ps)  : ', keycol)
        screen.addstr('%s'%(map(int, np.array(r.get('coarse_delays'), dtype=np.float32) / config['FEngine']['adc_clk'] * 1e6)), valcol)
        curline = min(ymax-1, curline+1)
        screen.addstr(curline, col, 'APPLIED DELAYS VALID AT: ', keycol)
        screen.addstr('%.1f seconds ago'%(time.time() - r.get('coarse_delays_valid_at')), valcol)

        # Observation info
        obs_info = r.get('CONTROL')['obs_def']
        obs_stat = r.get('CONTROL')['obs_status']
        curline = min(ymax-1, curline+2)
        screen.addstr(curline, col, 'OBSERVATION INFO')
        curline = min(ymax-1, curline+2)
        screen.addstr(curline, col, 'MODE : ', keycol)
        if obs_stat == 4:
            screen.addstr('observing', valcol)
        else:
            screen.addstr('not observing', errcol)
        curline = min(ymax-1, curline+1)
        screen.addstr(curline, col, 'NAME : ', keycol)
        screen.addstr('%s'%obs_info['name'], valcol)
        curline = min(ymax-1, curline+1)
        screen.addstr(curline, col, 'OBSERVER : ', keycol)
        screen.addstr('%s'%obs_info['observer'], valcol)
        curline = min(ymax-1, curline+1)
        screen.addstr(curline, col, 'FILE : ', keycol)
        screen.addstr('%s'%obs_info['file'], valcol)
        curline = min(ymax-1, curline+1)
        screen.addstr(curline, col, 'COMMENT : ', keycol)
        screen.addstr('%s'%obs_info['comment'].rstrip(), valcol)
        curline = min(ymax-1, curline+2)
        screen.addstr(curline, col, 'INTEGRATION TIME: ', keycol)
        screen.addstr('%.3f seconds'%get_int_time(config), valcol)
        curline = min(ymax-1, curline+2)
        
        for disk in ['/media/data0', '/media/data1']:
            ds = get_free_disk_space(disk)
            screen.addstr(curline, col, 'Available Disk Space on %s : '%disk, keycol)
            if ds < 200:
                screen.addstr('%.1f GB'%ds, errcol)
            else:
                screen.addstr('%.1f GB'%ds, valcol)
            curline = min(ymax-1, curline+1)

        #alert the used if we've run out of screen space
        if curline == ymax-1:
            screen.addstr(curline, col, 'WINDOW TOO SHORT!', errcol)
        

        screen.refresh()
        screen.getch()
        time.sleep(1)
        

if __name__ == '__main__':
    curses.wrapper(display_status, config_redis.JsonRedis('ami_redis_host'))
