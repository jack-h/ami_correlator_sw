import sys
import time
import numpy as np
import pylab
import ami.ami as AMI
import ami.helpers as helpers

if __name__ == '__main__':
    from optparse import OptionParser

    p = OptionParser()
    p.set_usage('%prog [options] [data file]')
    p.set_description(__doc__)

    opts, args = p.parse_args(sys.argv[1:])

    if args == []:
        print "Specify a data file!"
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

    time = time_fh.read()
    corr01 = np.fromstring(data01_fh.read(),dtype=complex)

    corr01 = corr01.reshape(corr01.shape[0]/2048,2048)
    samples,chans = corr01.shape
    print samples,'samples'
    print chans,'chans'

    #pylab.pcolor(np.angle(corr01[0:20]))
    pylab.imshow(np.angle(corr01[:,:]),aspect='auto')
    pylab.colorbar()
    pylab.title('Cross-correlation phase')
    pylab.xlabel('Freq. channel')
    pylab.ylabel('Time sample')
    pylab.show()
