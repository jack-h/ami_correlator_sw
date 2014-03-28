#!/usr/bin/env python

import numpy as np
import math, sys, os, h5py

if __name__ == '__main__':
    from optparse import OptionParser
    o = OptionParser()
    o.set_usage('%prog [options] *.h5')
    o.set_description(__doc__)
    o.add_option('-p', '--polyfit', dest='polyfit', action='store_true', default=False,
        help='Do a simple polynomial fit to identify and remove RFI')
    o.add_option('-a', '--autodiv', dest='autodiv', action='store_true', default=False,
        help='Divide cross correlation by sqrt(auto(0)*auto(1))')
    o.add_option('-O', '--overwrite', dest='overwrite', action='store_true', default=False,
        help='Overwrite output file if it already exists')
    o.add_option('-s', '--start', dest='start', type='int', default=0,
        help='Drop channels before this channel')
    o.add_option('-e', '--end', dest='end', type='int', default=-1,
        help='Drop channels after this channel')
    o.add_option('-S', '--swapri', dest='swapri', action='store_true',
        help='swap the real/imag components (for use with messed up data files pre 6pm 11/03/2014)')
    opts, args = o.parse_args(sys.argv[1:])
    if args==[]:
        print 'Please specify a hdf5 file! \nExiting.'
        exit()
    else:
        h5fns = args

def copy_attrs(fhi,fho):
    for a in fhi.attrs.iteritems():
        fho.attrs.create(a[0], a[1])

def append_history(fh,hist_str):
    if not('history' in fh.keys()):
        rv = fh.create_dataset('history', data=np.array([hist_str]))
    else:
        hv = fh['history'].value
        del fh['history']
        if type(hv) == np.ndarray: new_hist=np.append(hv,np.array([hist_str]))
        else: new_hist=np.array([[hv],[hist_str]])
        rv = fh.create_dataset('history', data=new_hist)

# Process data
for fni in args:
    fno = fni + '.preproc'
    if os.path.exists(fno):
        if not opts.overwrite:
            print 'File exists: skipping'
            continue
        else:
            print 'File exists: OVERWRITING!!!'
    print 'Opening:',fno
    fhi = h5py.File(fni, 'r')
    fho = h5py.File(fno, 'w')

    #copy attributes
    copy_attrs(fhi,fho)
    #copy datasets/groups except timestamps0 and xeng_raw0
    for item in fhi.iteritems():
        if item[0] == 'xeng_raw0':
            cm=fhi.get(item[0])[:,opts.start:opts.end,:,:,:] 
        else:
            if type(fhi[item[0]]) == h5py.highlevel.Group:
                tmp_grp = fhi.get(item[0])
                fho.copy(tmp_grp,item[0])
            else:
                fho.create_dataset(item[0],data=item[1])
    
    nchani=fhi.attrs['n_chans']
    if opts.start is None: ch_start=0
    else: ch_start=int(opts.start)
    if opts.end is None: ch_end=nchani
    else: ch_end=int(opts.end)
    n_ch = ch_end-ch_start

    nsa,nchan,nbl,npol,ncomp = cm.shape
    nants = fhi.attrs.get('n_ants')
    autos = np.zeros([nsa,nchan,nants,npol])
    bl_order = fhi.get('bl_order')

    #complexify
    if len(cm.shape) == 5:
        print "complexifying input data"
        cm = np.array(cm[:,:,:,:,1] + 1j*cm[:,:,:,:,0],dtype=np.complex128)

    #swap r/i
    if opts.swapri:
        print "swapping real/imag components"
        for bln,bls in enumerate(bl_order):
            if bls[0]!=bls[1]:
                cm[:,:,bln,:] = np.imag(cm[:,:,bln,:]) + 1j*np.real(cm[:,:,bln,:])

    if opts.autodiv:
        print "Dividing Cross-corrs by autos"
        #get the autocorrelations
        print "    Finding autos"
        for an in range(nants):
            for bln,bls in enumerate(bl_order):
                if bls[0]==bls[1]:
                    #This is an autocorrelation
                    autos[:,:,bls[0],:] = np.real(cm[:,:,bln,:])

        #Now we have the autos, divide the cross-corrs by them
        print "    Dividing crosses"
        for bln,bls in enumerate(bl_order):
            if bls[0] != bls[1]:
                #only divide the cross-corrs
                scale_fact = np.sqrt(autos[:,:,bls[0],:]*autos[:,:,bls[1],:])
                cm[:,:,bln,:] /= scale_fact

    if opts.polyfit:
        print "POLYFIT NOT YET IMPLEMENTED"
        cutoff=5
        print "Zapping values > %d*sigma"%cutoff
        for bln,bls in enumerate(bl_order):
            d_abs = np.abs(cm[:,:,bln,:])
            mean  = np.mean(d_abs)
            sigma = np.sqrt(np.var(d_abs))
            print bln,mean,sigma
            d_one_bl = cm[:,:,bln,:]
            d_one_bl[np.abs(d_one_bl[:,:,:]) > (mean+cutoff*sigma)] = 0
            cm[:,:,bln,:] = d_one_bl[:,:,:]

    
    #write ts and cm to file
    fho.create_dataset('xeng_raw0',data=cm)
    
    #write history log and update attributes
    sdf=fhi.attrs['bandwidth']/fhi.attrs['n_chans']
    fho.attrs['n_chans']=n_ch
    fho.attrs['bandwidth']=n_ch*sdf
    #sfreq=fhi.attrs['center_freq']-nchani/2*sdf
    sfreq=ch_start*sdf + (fhi.attrs['center_freq']-fhi.attrs['bandwidth']/2.)
    fho.attrs['center_freq']=sfreq+n_ch*sdf/2.
    print 'chan0 freq:', ch_start*sdf + (fhi.attrs['center_freq']-fhi.attrs['bandwidth']/2.)
    print 'chanN-1 freq:', ch_end*sdf + (fhi.attrs['center_freq']-fhi.attrs['bandwidth']/2.)
    print 'start freq:',sfreq
    print 'center freq:', fho.attrs['center_freq']
    print 'number of channels:',fho.attrs['n_chans']
    print 'bandwidth:',fho.attrs['bandwidth']
    hist_str ="PREPROC: Remove channels outside range [%d:%d]"%(ch_start,ch_end)
    if opts.polyfit: hist_str+="\n         Remove RFI by polynomial fit"
    if opts.autodiv: hist_str+="\n         Divide cross-corr by autos"
    if opts.swapri:  hist_str+="\n         Swapped real/imag parts"
    append_history(fho,hist_str)
    
    fho.close()
    fhi.close()
