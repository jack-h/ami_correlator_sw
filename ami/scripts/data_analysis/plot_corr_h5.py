#!/usr/bin/env python
"""
General plotting tool to plot SPEAD based correlator output
"""

import numpy, pylab, h5py, time, sys, math
import ephem

if __name__ == '__main__':
    from optparse import OptionParser
    o = OptionParser()
    o.set_usage('%prog [options] H5_DATA_FILE')
    o.set_description(__doc__)
    o.add_option('-a', '--ant', dest='ant', default=None,
        help='For corrected data with a bl table select which antennas to plot, <ant_i> will plot all bls with that antenna, <ant_i>_<ant_j> will plot that baseline, auto: plot auto correlations')
    o.add_option('-c', dest='chan_index', default='all',
        help='Select which channels to plot. Options are <ch_i>,...,<ch_j>, or a range <ch_i>_<ch_j>. Default=all')
    o.add_option('-i', '--index', dest='bl_index', default=0,
        help='Select which baseline index. Options are <bl0>,...,<bln>, or a range <bl0>_<bln>. Default=0')
    o.add_option('-m', '--mode', dest='mode', default='lin',
        help='Plotting mode: lin, log, real, imag, phs, comp. Default=log')
    o.add_option('-p', '--pol', dest='pol', default='all',
        help='Select which polarization to plot (xx,yy,xy,yx,all). Default=all')
    o.add_option('--timescale', dest='time_scale', type='string', default='time',
        help='Select unit of time axis. time=hours since reference. ha=hour angle. lst=lst of observatory')
    o.add_option('-r', '--ra', type='string', default='23:23:58.45',
        help='RA of source (only for use when plotting transits or hour angles). Format is HH:MM:SS.S')
    o.add_option('-d', '--decimate', dest='decimate', default=1,
        help='Decimate in time by N samples to speed up plotting, Default=None')
    o.add_option('-t', '--time', dest='time', default=None, help='Select which time samples to plot, <t_i> or <t_i>,<t_j>,... or if in waterfall mode <t_0>_<t_k>. Default: all times')
    o.add_option('-w','--water', dest='water', default=False, action='store_true',
        help='Produce a waterfall plot of a time range using -t <t_0>_<t_n>')
    o.add_option('-u', '--unmask', dest='unmask', default=False, action='store_true',
        help='Plot the raw data.')
    o.add_option('-n', '--normalise', dest='normalise', action='store_true', default=False,
        help='Use the --normalise flag to scale 0db to the maximum value in the plot.')
    o.add_option('--namemap', dest='namemap', default=None,
        help='Pass a file with a list of human-readable names for antennas')
    o.add_option('-f', '--freqaxis', dest='freqaxis', default=False, action='store_true',
        help='Plot frequency or delay (rather than channel) as x axis.')
    o.add_option('--make_unique', dest='make_unique', default=False, action='store_true',
        help='use this option to prevent duplicate plotting')
    o.add_option('-s', '--savefig', dest='savefig', default=None,
        help='Name with which to save figure.')
    o.add_option('--chan', dest='chan_time', action='store_true',
        help='Plot individual channels as a function of time')
    o.add_option('--legend', dest='legend', default=None,
        help='Show a legend at specified position. e.g. --legend "best" ')
    o.add_option('--share', dest='share', action='store_true',
        help='Share plots in a single frame.')
    o.add_option('-D', '--delay', dest='delay', action='store_true',
        help='Take FFT of frequency axis to go to delay (t) space.')
    o.add_option('-F', '--fringe', dest='fringe', action='store_true',
        help='Take FFT of time axis to go to fringe (Hz) space.')
    o.add_option('--shape', dest='shape', default=None,
        help='x_y dimensions of subplot. Default: squareish')
    opts, args = o.parse_args(sys.argv[1:])
    if args==[]:
        print 'Please specify a hdf5 file! \nExiting.'
        exit()
    else:
        fnames = args

#Helper function to read hdf5 attributes
def get_attr(fh,attr):
    if attr in fh.attrs.keys():
        rv = fh.attrs.get(attr)
    elif attr in fh.keys():
        # sometimes there's a glitch in the matrix and attributes end up packed as datasets
        # TODO: fix this at the source
        print 'WARNING: tried to get attribute %s and failed. Trying to extract from data set.'%attr
        print fh.get(attr)[-1]
        rv = fh.get(attr)[-1] #use the latest value in the dataset
    else:
        print 'ERROR: could not find attribute %s in hdf5 file' %attr
    return rv

def nameremap(fn):
    """read a file with a map of antenna numbers to useful names"""
    fh = open(fn,'r')
    namemap = fh.read().split('\n')
    fh.close()
    return namemap

def convert_arg_range(arg):
    """Split apart command-line lists/ranges into a list of numbers."""
    arg = arg.split(',')
    init = [map(int, option.split('_')) for option in arg]
    rv = []
    for i in init:
        if len(i) == 1:
            rv.append(i[0])
        elif len(i) == 2:
            rv.extend(range(i[0],i[1]+1))
    return rv

def convert_ant(arg,bl_order):
    """Return a list of baselines to plot"""
    arg = arg.split(',')
    rv = []
    if arg[0]=='all':
        for b,bl in enumerate(bl_order): rv.append(b)
    elif arg[0]=="auto":
        for b,bl in enumerate(bl_order):
            if bl[0]==bl[1]: rv.append(b)
    else:
        init = [map(int, option.split('_')) for option in arg]
        for i in init:
            if len(i) == 1:
                for b,bl in enumerate(bl_order):
                    if (i==bl[0]) | (i==bl[1]): rv.append(b)
            elif len(i) == 2:
                for b,bl in enumerate(bl_order):
                    if (i[0]==bl[0] and i[1]==bl[1]) | (i[1]==bl[0] and i[0]==bl[1]): rv.append(b)
    return rv

def tup_bls(bls):
    rv=[]
    for i,j in bls:
        rv.append((i,j))
    rv=tuple(rv)
    return rv

pol_map = {'xx':0,'yy':1,'xy':2,'yx':3}
map_pol = ['xx','yy','xy','yx']
def convert_pol(arg):
    """Parse polarization options"""
    if arg == 'all':
        return [pol_map['xx'], pol_map['yy'], pol_map['xy'], pol_map['yx']]
    else:
        arg = arg.split(',')
        rv = []
        for pi in arg: rv.append(pol_map[pi])
        return rv

def get_freq_range(fh,delay=False):
    """return array of frequency channel bin center values"""
    cf = fh.attrs.get('center_freq')
    n_chans = fh.attrs.get('n_chans')
    bw = fh.attrs.get('bandwidth')
    start_freq = cf - (bw/2)
    bin_width = bw/float(n_chans)
    freq_range = numpy.arange(start_freq,start_freq+bw,bw/n_chans)
    delay_max = 1./(2*bin_width)*1e3 # in nanoseconds
    delay_range = numpy.arange(-delay_max,delay_max,2*delay_max/n_chans)
    funit = 'MHz'
    dunit = 'ns'
    if delay:
        return 'Delay',dunit,delay_range
    else:
        return 'Frequency',funit,freq_range

def gen_obs(lat=None,long=None,el=0,telescope=None):
    obs = ephem.Observer()
    if telescope == 'Medicina' or telescope == 'MEDICINA':
        obs.lat = '44:31:24.88'
        obs.long = '11:38:45.56'
    if telescope == 'AMI':
        obs.lat = '52:10:14.2'
        obs.long = '0:2:20.0'
    elif ((lat is not None) and (long is not None)):
        obs.lat = lat
        obs.long = long
    else:
        raise ValueError("Unknown observatory: %s" %telescope)
    return obs

def gen_time_axis(timestamps,scale,offset):
    """ Return a list of real times from the timestamp vector"""
    # get the timestamps
    timestamps = numpy.array(timestamps, dtype=float)
    t = numpy.zeros(len(timestamps),dtype=numpy.float64)
    t = numpy.array(offset + timestamps/scale,dtype=numpy.float64) #UNIX times
    t_range = t[-1] - t[0]
    gmt_ref = time.gmtime(t[0]) # Start time in UTC
    jd_ref = ephem.julian_date(gmt_ref[0:6])

    if t_range < 300:
        scale = 'Seconds since %.4d/%.2d/%.2d %.2d:%.2d:%.2d UTC' %(gmt_ref[0:6])
        t = (t-t[0])
    elif t_range < 60*60*3:
        scale = 'Minutes since %.2d/%.2d/%.2d %.2d:%.2d:%.2d UTC' %(gmt_ref[0:6])
        t = (t-t[0])/60
    else:
        scale = 'Hours since %.2d/%.2d/%.2d %.2d:%.2d:%.2d UTC' %(gmt_ref[0:6])
        t = (t-t[0])/60/60
    return {'times':t, 'scale':scale, 'ref':t[0], 'gmtref':gmt_ref, 'jd_ref':jd_ref, 'unit':''}

def gen_ha_axis(timestamps,scale,offset,RA):
    """ Return a list of real times from the timestamp vector"""
    # get the timestamps
    timestamps = numpy.array(timestamps, dtype=float)
    t = numpy.zeros(len(timestamps),dtype=numpy.float64)
    t = numpy.array(offset + timestamps/scale,dtype=numpy.float64) #UNIX times
    gmt_ref = time.gmtime(t[0]) # Start time in UTC
    jd_ref = ephem.julian_date(gmt_ref[0:6])
    ha = numpy.zeros_like(t)
    for i,ti in enumerate(t):
        obs.date = ephem.Date(time.gmtime(ti)[0:6])
        #print "time is", obs.date
        ha[i] = obs.sidereal_time() - RA
        #print obs.sidereal_time(), RA, obs.sidereal_time()-RA
    # Unwrap the phases, otherwise weird things can happen
    # When the lst crosses midnight
    ha = numpy.unwrap(ha)
    ha = numpy.rad2deg(ha)
    if RA == 0:
        scale = 'Local Sidereal Time'
    else:
        scale = 'Hour Angle'
    return {'times':ha, 'scale':scale, 'ref':RA, 'gmtref':gmt_ref, 'jd_ref':jd_ref, 'unit':''}


bl_order=None
decimate=int(opts.decimate)
flags=None

n_files = len(fnames)
for fi, fname in enumerate(fnames):
    print "Opening:",fname, "(%d of %d)"%(fi+1,len(fnames))
    fh = h5py.File(fname, 'r')
    timestamps = fh.get('timestamp0')
    if opts.time is None:
        time_index=range(len(timestamps))
    else: time_index = convert_arg_range(opts.time)
    if decimate>1:
        time_index=time_index[::decimate]
    if fi==0:
        # Generate the ephem Observer from the location of the observatory in the file
        try: telescope = get_attr(fh,'telescope')
        except: telescope = 'AMI'

        try: source = get_attr(fh,'obs_name')
        except: source = None
        print 'Telescope: %s' %telescope
        print 'Source: %s' %source
        if opts.time_scale=='ha' or opts.time_scale=='lst':
            #if we are plotting hour angles we need to know where the observatory is
            obs = gen_obs(telescope=telescope)
        # get the frequency axis
        axis_name, freq_unit, freq_range = get_freq_range(fh,delay=opts.delay)
        if 'pol' in fh.keys() and opts.pol.startswith('all'):
            unique_pols = list(numpy.unique(fh['pol']))
            pols = []
            for pi in unique_pols: pols.append(pol_map[pi])
        else: pols = convert_pol(opts.pol)
        
        if 'bl_order' in fh.keys() and opts.ant:
            bl_order = fh['bl_order'].value
            bl_index = convert_ant(opts.ant, bl_order)
            bl_order=tup_bls(bl_order)
        if not opts.ant:
            bl_index = convert_arg_range(opts.bl_index)
        
        #make the index list unique
        #this is an option, since making the vector unique
        #messes with its order
        if opts.make_unique:
            bl_index=numpy.unique(bl_index)
        
        if opts.shape is None:
            m2 = int(math.sqrt(len(bl_index)))
            m1 = int(math.ceil(float(len(bl_index)) / m2))
        else:
            m2,m1=map(int,opts.shape.split('_'))
        
        n_ants = fh.attrs.get('n_ants')
        if opts.chan_index == 'all': chan_index = range(0,fh.attrs.get('n_chans'))
        else: chan_index = convert_arg_range(opts.chan_index)
        if opts.freqaxis:
            freq_range = freq_range[chan_index]
        else:
            freq_range = chan_index
            freq_unit = 'channel'
   
        d = fh.get('xeng_raw0')[time_index][:,chan_index][:,:,bl_index][:,:,:,pols]
        t = fh.get('timestamp0')[time_index]
        if 'flags' in fh.keys() and not opts.unmask:
            flags = fh['flags'][time_index][:,chan_index][:,:,bl_index][:,:,:,pols]
    else:
        d = numpy.concatenate((d, fh.get('xeng_raw0')[time_index][:,chan_index][:,:,bl_index][:,:,:,pols]))
        t = numpy.append(t,fh.get('timestamp0')[time_index])
        if 'flags' in fh.keys() and not opts.unmask:
            flags = numpy.concatenate((flags, fh['flags'][time_index][:,chan_index][:,:,bl_index][:,:,:,pols]))
    if fi==n_files-1:
        #Generate proper times
        #Unlike S-engine files, X-engine timestamps are already UNIX times
        scale_factor = 1.
        offset = 0.
        if opts.time_scale == 'time':
            t = gen_time_axis(t,scale_factor,0)
        elif opts.time_scale == 'ha':
            t = gen_ha_axis(t,scale_factor,offset,ephem.hours(opts.ra))
        else: 
            t = gen_ha_axis(t,scale_factor,offset,0.0)
    fh.flush()
    fh.close()

y_label=''
fig = pylab.figure()
print m2,m1
total_plots = len(bl_index)
for cnt,bl in enumerate(bl_index):
    if not opts.share:
        pylab.subplot(m2, m1, cnt+1)
        print cnt+1
        if ((cnt+1)%m1 == 1) or (m1==1):
            first_col = True
        else:
            first_col = False
        if (cnt>=total_plots-m1):
            bottom_row = True
        else:
            bottom_row = False

        dmin,dmax = None,None
    for pi,pol in enumerate(pols):
        #real: 1
        #imag: 0
        di = d[:,:,cnt,pi,1] + d[:,:,cnt,pi,0]*1j
        if flags != None:
            print di.shape
            di=numpy.ma.array(di,mask=flags[:,:,cnt,pi])
            di=di.filled(0)
        if opts.delay:
            di = numpy.fft.ifft(di,axis=1)
            di = numpy.concatenate([di[:,di.shape[1]/2:], di[:,:di.shape[1]/2]], axis=1)
        if opts.fringe:
            di = numpy.fft.ifft(di,axis=0)
            di = numpy.ma.concatenate([di[di.shape[0]/2:], di[:di.shape[0]/2]], axis=0)
        if opts.mode.startswith('lin'):
            di = numpy.absolute(di)
            if opts.normalise:
                print 'Normalising maximum value to 0dB'
                di /= numpy.max(di)
                y_label = 'Normalized power'
                ymin=1e-4
            else:
                y_label = 'Power (DBU)'
        if opts.mode.startswith('log'):
            di = numpy.absolute(di)
            if opts.normalise:
                print 'Normalising maximum value to 0dB'
                di /= numpy.max(di)
                y_label = 'log(Normalized power)'
                ymin=-4
            else:
                y_label = 'log(Power)'
            di = numpy.log10(di)
        if opts.mode.startswith('db'):
            di = numpy.absolute(di)
            if opts.normalise:
                print 'Normalising maximum value to 0dB'
                di /= numpy.max(di)
                y_label = 'Normalized Power (dB)'
                ymin=-40
            else:
                y_label = 'dB (arbitrary reference)'
            di = 10*numpy.log10(di)
        if opts.mode.startswith('real'): di = di.real
        if opts.mode.startswith('imag'): di = di.imag
        if opts.mode.startswith('ph'):
            di = numpy.angle(di)

        label = str(bl_order[bl]) + str(map_pol[pi])
        if not opts.share:
            if opts.mode.startswith('comp'):
                if di.real.max()>dmax: dmax=di.real.max()
                if di.real.min()<dmin: dmin=di.real.max()
                if di.imag.max()>dmax: dmax=di.imag.max()
                if di.imag.min()<dmin: dmin=di.imag.max()
            else:
                if di.max()>dmax: dmax=di.max()
                if di.min()<dmin: dmin=di.max()
        print '.',
        sys.stdout.flush()
        if opts.water:
            frange = float(freq_range[-1] - freq_range[0])
            nchans = len(freq_range)
            bin_width = frange/nchans
            extent_min = freq_range[0]
            extent_max = freq_range[-1]
            if opts.mode.startswith('phs'):
                im = pylab.imshow(di, vmin=-numpy.pi, vmax=numpy.pi, aspect='auto',extent=(extent_min,extent_max,di.shape[0],0))
                pylab.set_cmap('hsv')
            else:
                im = pylab.imshow(di, aspect='auto',extent=(extent_min,extent_max,di.shape[0],0))
            #pylab.pcolor(di)


            # Set the x axis to be hours/mins/secs
            if opts.time_scale == 'ha' or opts.time_scale == 'lst':
                yticks_loc, yticks_labels = pylab.yticks()
                yticks_loc = yticks_loc[1:-1]
                yticks_labels = []
                for y in yticks_loc:
                    ra_hours = '%s' %ephem.hours(numpy.deg2rad(t['times'][y]))
                    hours, mins, secs = map(float,ra_hours.split(':'))
                    yticks_labels.append('$%.0f^{\mathrm{h}} %d^{\mathrm{m}} %d^{\mathrm{s}}$' %(hours,mins,secs))
                pylab.yticks(yticks_loc, yticks_labels)
            # get rid of uneeded axes
            if not first_col:
                ticks_loc,ticks = pylab.yticks()
                pylab.yticks(ticks_loc,['']*len(ticks_loc))
            if not bottom_row:
                ticks_loc,ticks = pylab.xticks()
                pylab.xticks(ticks_loc,['']*len(ticks_loc))

        else:
            if opts.chan_time:
                for c in range(len(chan_index)):
                    if opts.namemap is None:
                        pylab.plot(t['times'],di[:,c])
                    else:
                        remap = nameremap(opts.namemap)
                        ant0 = remap[bl_order[bl][0]]
                        ant1 = remap[bl_order[bl][1]]
                        label_str = '%s - %s'%(ant0,ant1)
                        pylab.plot(t['times'],di[:,c],label=label_str)
                if opts.normalise:
                    pylab.ylim(ymin=ymin)
                pylab.xlabel(t['scale']+' %s'%t['unit'])
                pylab.ylabel(y_label)
                
                # Set the x axis to be hours/mins/secs
                if opts.time_scale == 'ha' or opts.time_scale == 'lst':
                    xticks_loc, xticks_labels = pylab.xticks()
                    xticks_labels = []
                    for x in xticks_loc:
                        ra_hours = '%s' %ephem.hours(numpy.deg2rad(x))
                        hours, mins, secs = map(float,ra_hours.split(':'))
                        xticks_labels.append('$%.0f^{\mathrm{h}} %d^{\mathrm{m}} %d^{\mathrm{s}}$' %(hours,mins,secs))
                    pylab.xticks(xticks_loc, xticks_labels)
            else:
                for t in range(len(time_index)):
                    #pylab.plot(di[t], '.', label=label)
                    if opts.mode.startswith('comp'):
                        pylab.plot(freq_range,di[t].real)
                        pylab.plot(freq_range,di[t].imag)
                    else: pylab.plot(freq_range,di[t])
                pylab.xlim(freq_range[0],freq_range[-1])
                pylab.xlabel('%s (%s)'%(axis_name,freq_unit))
                pylab.ylabel('%s'%y_label)
                    #pylab.plot(di[t], label=label)

    if not opts.share and not opts.water:
        pylab.ylim(dmin,dmax)
    if not opts.share:
        if opts.namemap is None:
            pylab.title(bl_order[bl])
        else:
            remap = nameremap(opts.namemap)
            ant0 = remap[bl_order[bl][0]]
            ant1 = remap[bl_order[bl][1]]
            title_str = '%s - %s'%(ant0,ant1)
            pylab.title(title_str)

if opts.legend is not None:
    if opts.legend == 'best':
        pylab.legend(loc=opts.legend)
    else:
        pylab.legend(loc=int(opts.legend))
#if opts.water: pylab.colorbar()
print 'done'
if opts.water:
    pylab.subplots_adjust(wspace=0.04)
else:
    pylab.subplots_adjust(hspace=0.5)
if opts.water:
    left_shift = 0.17
    bottom_shift = 0.20
    if opts.mode.startswith('phs'):
        pi = numpy.pi
        ticks = numpy.arange(-pi,pi+1e-5,pi/4.)
        tick_names = ['$-\\pi$',
                      '$-\\frac{3\\pi}{4}$',
                      '$-\\frac{\\pi}{2}$',
                      '$-\\frac{\\pi}{4}$',
                      '$0$',
                      '$\\frac{\\pi}{4}$',
                      '$\\frac{\\pi}{2}$',
                      '$\\frac{3\\pi}{4}$',
                      '$\\pi$'
                      ]
        #pylab.imshow(np.zeros([2,2]),vmin=-pi,vmax=pi)
        pylab.subplots_adjust(bottom=bottom_shift)
        cbar_ax = fig.add_axes([left_shift,0.10,1-left_shift-0.1,0.03])
        cb = pylab.colorbar(im, cax=cbar_ax,orientation='horizontal',ticks=ticks)
        cb.ax.set_xticklabels(tick_names,fontsize=20)
        #increase the font size
    else:
        pylab.colorbar()
    # add a single axis label for all subplots
    pylab.subplots_adjust(left=left_shift)
    yax = fig.add_axes([0,bottom_shift,left_shift,1.-bottom_shift-0.1])
    yax.set_axis_off()
    yax.set_xlim(0,1)
    yax.set_ylim(0,1)
    yax.text(0.25,0.5,t['scale']+' %s'%t['unit'],rotation='vertical',
             horizontalalignment='center', verticalalignment='center')
    xax = fig.add_axes([left_shift,0.13,1-left_shift-0.1,bottom_shift-0.13])
    xax.set_axis_off()
    xax.set_xlim(0,1)
    xax.set_ylim(0,1)
    xax.text(0.5,0.5,'%s (%s)'%(axis_name,freq_unit),
                 horizontalalignment='center', verticalalignment='top')

if opts.savefig is not None:
    pylab.savefig(opts.savefig, bbox_inches='tight')
pylab.show()



