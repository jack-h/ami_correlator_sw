import sys
import time
import numpy as np
import h5py
import pylab

if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('%prog [options] [data file]')
    p.set_description(__doc__)

    opts, args = p.parse_args(sys.argv[1:])

    if len(args) != 1:
        print "Specify one data file!"
        exit()
    else:
        fname = args[0]

    # do some stripping of the file extensions. Too lazy for regex
    fname = fname.rstrip('.dat00')
    fname = fname.rstrip('.dat11')
    fname = fname.rstrip('.dat01')
    fname = fname.rstrip('.timedat')
    fname = fname.rstrip('.')

    data00_fh = open(fname+'.dat00','rb')
    data11_fh = open(fname+'.dat11','rb')
    data01_fh = open(fname+'.dat01','rb')
    time_fh = open(fname+'.timedat','rb')

    #time_str = time_fh.read()
    #time = np.fromstring(time_str[0:times],dtype=np.int64)
    corr01 = np.fromstring(data01_fh.read(),dtype=complex)
    corr00 = np.fromstring(data00_fh.read(),dtype=np.int64)
    corr11 = np.fromstring(data11_fh.read(),dtype=np.int64)


    # open the h5 file
    h5_fh = h5py.File(fname+'.h5', mode='w')
    # Some hard coded parameters (this script is only temporary, until the receiver writes h5 directly
    N_CHANS = 2048
    N_POLS = 1
    N_BLS = 3
    N_ANTS = 2
    bl_order = [[0,0],[1,1],[0,1]]
    CENTER_FREQ = 10e9
    BANDWIDTH = 2e9

    corr01 = corr01.reshape(corr01.shape[0]/N_CHANS,N_CHANS)
    corr11 = corr11.reshape(corr11.shape[0]/N_CHANS,N_CHANS)
    corr00 = corr00.reshape(corr00.shape[0]/N_CHANS,N_CHANS)
    samples,chans = corr01.shape
    print samples,'samples'
    print chans,'chans'

    #create the data array
    #store complex values in two parts, since this is what the plotting script expects
    h5_fh.create_dataset('xeng_raw0',shape=[samples,N_CHANS,N_BLS,N_POLS,2],dtype=np.int64)
    h5_fh['xeng_raw0'][:,:,0,0,0] = np.real(corr00)
    h5_fh['xeng_raw0'][:,:,0,0,1] = np.imag(corr00)
    h5_fh['xeng_raw0'][:,:,1,0,0] = np.real(corr11)
    h5_fh['xeng_raw0'][:,:,1,0,1] = np.imag(corr11)
    h5_fh['xeng_raw0'][:,:,2,0,0] = np.real(corr01)
    h5_fh['xeng_raw0'][:,:,2,0,1] = np.imag(corr01)

    # array of timestamps in unix time
    h5_fh.create_dataset('timestamp0',shape=[samples],dtype=float)
    base_time = float(fname[-13:])
    print 'base_time', base_time
    time_scale = 8./2e9
    acc_len = 8*100000*N_CHANS / 2e9
    print "Hard coded accumulation length!!!!", acc_len
    time_vec = base_time + (np.arange(samples)*acc_len*4)
    print time_vec
    h5_fh['timestamp0'][:] = time_vec

    #set some attributes
    h5_fh.attrs['n_chans'] = N_CHANS
    h5_fh.attrs['n_pols'] = N_POLS
    h5_fh.attrs['n_bls'] = N_BLS
    h5_fh.attrs['n_ants'] = N_ANTS
    h5_fh.create_dataset('bl_order',shape=[3,2],dtype=int,data=bl_order)
    h5_fh.attrs['center_freq'] = CENTER_FREQ
    h5_fh.attrs['bandwidth'] = BANDWIDTH

    data00_fh.close()
    data11_fh.close()
    data01_fh.close()
    time_fh.close()
    h5_fh.close()
