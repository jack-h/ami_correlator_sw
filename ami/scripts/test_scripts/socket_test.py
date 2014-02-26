import socket
import struct
import numpy as np
import time

def check_new_connections(sock):
    try:
        conn,addr = sock.accept()
        print "New connection established", addr
        return conn
    except socket.timeout:
        pass

def try_recv_from_all(socks):
    data_all = []
    success = 0
    for sn,s in enumerate(socks):
        # Test for dead connections and close them
        try:
            s.send(struct.pack('!i',0))
            data = s.recv(BUFFER_SIZE)
            data_all.append(data)
            success += 1
        except socket.error:
            print "Lost RX connection"
            s.close()
            socks.pop(sn)
    return success, data_all

def try_send_to_all(socks,string):
    success=0
    for sn,s in enumerate(socks):
        try:
            s.send(string)
            success += 1
        except socket.error:
            print "lost TX connection"
            s.close()
            socks.pop(sn)
    return success

class AmiMetaData(object):
    def __init__(self,nants=10,nagcs=40):
        """
        A simple class of which allows unpacking of data into
        specific attributes, some with array formatting
        """
        self.nants = nants
        self.nagcs = nagcs
        self.entries= [
                  {'name':'timestamp', 'form':'!l'},
                  {'name':'obs_status','form':'!4xi'},
                  {'name':'obs_name',  'form':'!32s'},
                  {'name':'nsamp',     'form':'!i'},
                  {'name':'ha_reqd',   'form':'!%di'%self.nants},
                  {'name':'ha_read',   'form':'!%di'%self.nants},
                  {'name':'dec_reqd',  'form':'!%di'%self.nants},
                  {'name':'dec_read',  'form':'!%di'%self.nants},
                  {'name':'pc_value',  'form':'!%di'%self.nants},
                  {'name':'pc_error',  'form':'!%di'%self.nants},
                  {'name':'rain_data', 'form':'!%di'%self.nants},
                  {'name':'tcryo',     'form':'!%di'%self.nants},
                  {'name':'pcryo',     'form':'!%di'%self.nants},
                  {'name':'agc',       'form':'!%di'%self.nagcs},
                 ]
        self.gen_offsets()

    def gen_offsets(self):
        offset = 0
        for entry in self.entries:
            entry['offset'] = offset
            offset += struct.calcsize(entry['form'])

    def extract_attr(self,data):
        """
        update the attributes with the values packed in 'data'
        """
        for entry in self.entries:
            self.__setattr__(entry['name'],struct.unpack_from(entry['form'],data,entry['offset']))


class DataStruct(struct.Struct):
    """
    A subclass of Struct to encapsulate correlator data and timestamp
    """
    def __init__(self, nchans=2048):
        form = 'l%dl'%(2*nchans)
        struct.Struct.__init__(self,form)

if __name__ == "__main__":

    TCP_IP = '127.0.0.1' #The IP address on this machine to bind to
    TCP_PORT_T = 2006    #The port to send to
    TCP_PORT_R = 2007    #The port to receive on
    BUFFER_SIZE = 568    #Number of bytes in a struct from AMI control PC
    
    ami_meta_data = AmiMetaData()
    ami_data = DataStruct()
    
    # Open the receiver socket
    ssock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ssock.bind((TCP_IP,TCP_PORT_T))
    ssock.settimeout(0.0001)
    #ssock.setblocking(0)
    ssock.listen(1)
    
    # Open the transmitter socket
    tsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tsock.bind((TCP_IP,TCP_PORT_R))
    tsock.settimeout(0.0001)
    #tsock.setblocking(0)
    tsock.listen(1)
    
    cnt = 0
    conns_r = []
    conns_t = []
    
    try:
        while(True):
            time.sleep(0.01)
            ##### receive code #####
            suc, all_data = try_recv_from_all(conns_r)
            for data in all_data:
                if data>0:
                    ami_meta_data.extract_attr(data)
                    print 'timestamp ',ami_meta_data.timestamp 
                    print 'obs_status',ami_meta_data.obs_status
                    print 'obs_name  ',ami_meta_data.obs_name  
                    print 'nsamp     ',ami_meta_data.nsamp     
                    print 'ha_reqd   ',ami_meta_data.ha_reqd   
                    print 'ha_read   ',ami_meta_data.ha_read   
                    print 'dec_reqd  ',ami_meta_data.dec_reqd  
                    print 'dec_read  ',ami_meta_data.dec_read  
                    print 'pc_value  ',ami_meta_data.pc_value  
                    print 'pc_error  ',ami_meta_data.pc_error  
                    print 'rain_data ',ami_meta_data.rain_data 
                    print 'tcryo     ',ami_meta_data.tcryo     
                    print 'pcryo     ',ami_meta_data.pcryo     
                    print 'agc       ',ami_meta_data.agc       
                    print ''
        
            ##### send code #####
            # construct the output data and try to send it,
            # catching and killing any dead connections
            corrdata = np.ones(2048*2,dtype=np.int32)*cnt
            tx_str = ami_data.pack(cnt,*corrdata)
            cnt += try_send_to_all(conns_t,tx_str)
        
            ##### New connections #####
            # On each pass poll for new connections.
            newconn = check_new_connections(tsock)
            if newconn is not None: conns_t.append(newconn)
            newconn = check_new_connections(ssock)
            if newconn is not None: conns_r.append(newconn)
    except KeyboardInterrupt:
        print "Closing connections"
        for r in conns_r: r.close()
        for t in conns_t: t.close()
        ssock.close()
        tsock.close()
