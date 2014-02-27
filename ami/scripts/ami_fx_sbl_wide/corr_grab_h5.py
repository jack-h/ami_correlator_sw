import sys
import time
import numpy as np
import adc5g as adc
import pylab
import socket
import ami.ami as AMI
import ami.helpers as helpers
import ami.amisa_control as control
import ami.file_writer as fw

def write_data(writer, d, timestamp, meta):
    for entry in meta.entries:
       name = entry['name']
       if name is not 'obs_name':
           val = meta.__getattribute__(name)
           try:
               length = len(val)
           except TypeError:
               length = 1
           writer.append_data(name, [length], val)
    writer.append_data('xeng_raw0', d.shape, d)
    writer.append_data('timestamp0', [1], timestamp)


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

    writer = fw.H5Writer(config_file=config_file)
    writer.set_bl_order([[0,0],[1,1],[0,1]])

    ctrl = control.AmiControlInterface(config_file=config_file)
    ctrl.connect_sockets()

    # first get some meta data, as this encodes the source name
    # which we will use to name the output file

    while (ctrl.try_recv() is None):
        print "Waiting for meta data"
        time.sleep(1)

    print "Got meta data"
    print "Current status", ctrl.meta_data.obs_status
    print "Current source", ctrl.meta_data.obs_name

    corr = AMI.AmiSbl(config_file=config_file, verbose=True, passive=True)
    time.sleep(0.1)

    xeng = corr.xengs[0]
    cnt=0
    datavec = np.zeros([corr.n_chans,corr.n_bls,corr.n_pols,2],dtype=np.int64)
    current_obs = None
    mcnt_old = xeng.read_uint('mcnt_lsb')
    receiver_enable = False
    while(True):
        try:
            if (ctrl.try_recv()==0):
                cnt+=1
                print "received metadata with timestamp", ctrl.meta_data.timestamp
                receiver_enable = bool(ctrl.meta_data.obs_status)
                if ctrl.meta_data.obs_status == 0:
                    print "OBS STATUS == 0"
                    #set current obs to none so the next valid obs will trigger a new file
                    current_obs = None
                    writer.close_file()
                    continue
                if ctrl.meta_data.obs_name != current_obs:
                    writer.close_file()
                    fname = 'corr_%s_%d.h5'%(ctrl.meta_data.obs_name, ctrl.meta_data.timestamp)
                    print "Starting a new file with name", fname
                    writer.start_new_file(fname)
                    writer.add_attr('obs_name',ctrl.meta_data.obs_name)
                    current_obs = ctrl.meta_data.obs_name
            if receiver_enable:
                mcnt = xeng.read_uint('mcnt_lsb')
                if mcnt != mcnt_old:
                    mcnt_old = mcnt
                    d = corr.snap_corr(wait=False,combine_complex=False)
                    datavec[:,0,0,0] = d['corr00']
                    datavec[:,1,0,0] = d['corr11']
                    datavec[:,2,0,0] = d['corr01'][0::2]
                    datavec[:,2,0,1] = d['corr01'][1::2]
                    print "got new data with timestamp",d['timestamp']
                    ctrl.try_send(d['timestamp'],cnt,cnt,d['corr01'])
                    write_data(writer,datavec,d['timestamp'],ctrl.meta_data)
                    #cnt += 1
        except KeyboardInterrupt:
            print 'Received keyboard interrupt. Closing files and exiting'
            writer.close_file()
            ctrl.close_sockets()
            exit()
        time.sleep(0.1)



