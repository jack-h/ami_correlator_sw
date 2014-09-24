import struct
import configparser
import socket
import os
import string
import config_redis
import yaml

class AmiControlInterface(object):
    """
    A class for the interface between the AMI digital correlator
    and the original analogue correlator control machine.
    This handles passing meta data messages to the digital correlator
    and digital correlator data sets to the original pipeline
    """
    def __init__(self,config_file=None):
        """
        Initialise the interface, based on the config_file provided, or the AMI_DC_CONF
        environment variable is config_file=None
        """
        self.redis_host = config_redis.JsonRedis('ami_redis_host')
        if config_file is None:
            self.config = yaml.load(self.redis_host.hget('config', 'conf'))
            host = self.redis_host.hget('config', 'host')
            fn = self.redis_host.hget('config', 'file')
            config_file = '%s:%s'%(host, fn)
        else:
            self.config = yaml.load(config_file)
        self.parse_config_file()
        self.bind_sockets()
        self.meta_data = AmiMetaData(n_ants=self.n_ants,n_agcs=self.n_agcs)
        self.data = DataStruct(n_chans=self.n_chans*self.n_bands)

    def __del__(self):
        try:
            self.close_sockets()
        except:
            pass
    def parse_config_file(self):
        """
        Parse the config file, saving some values as attributes for easy access
        """
        #relevant parameters
        self.control_ip = self.config['Configuration']['control_interface']['host']
        self.data_port  = self.config['Configuration']['control_interface']['data_port']
        self.meta_port  = self.config['Configuration']['control_interface']['meta_port']
        self.n_ants      = self.config['Configuration']['control_interface']['n_ants']
        self.n_agcs      = self.config['Configuration']['control_interface']['n_agcs']
        self.n_chans     = self.config['Configuration']['correlator']['hardcoded']['n_chans']
        self.n_bands     = self.config['Configuration']['correlator']['hardcoded']['n_bands']
    def bind_sockets(self):
        """
        Bind the sockets to the data and metadata server
        """
        self.rsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    def close_sockets(self):
        """
        close the sockets
        """
        self.tsock.close()
        self.rsock.close()
    def connect_sockets(self):
        """
        Connect the tx/rx sockets to the correlator control server
        """
        self.rsock.settimeout(1.00)
        self.rsock.connect((self.control_ip,self.meta_port))
        self.rsock.settimeout(0.01)
        self.tsock.settimeout(1.00)
        self.tsock.connect((self.control_ip,self.data_port))
        self.tsock.settimeout(0.01)
    def try_recv(self):
        """
        Try and receive meta-data from the control server.
        Return None if the read times out, or 0 if the read
        is successful. Unpack read data into meta data attributes
        """
        try:
            d = self.rsock.recv(self.meta_data.size)
        except socket.timeout:
            return None
        if len(d) == self.meta_data.size:
            self.meta_data.extract_attr(d)
            return 0
    def try_send(self, timestamp, status, nsamp, d):
        """
        Try and send a data set to the control server.
        Return 0 if successful, -1 if not (and close tx socket)
        """
        data_str = self.data.pack(timestamp, status, nsamp, *d)
        try:
            self.tsock.send(data_str)
            return 0
        except socket.error:
            print "lost TX connection"
            self.tsock.close()
            return -1

        
class AmiMetaData(object):
    """
    A class encapsulating AMI meta data properties
    """
    def __init__(self,n_ants=10,n_agcs=40):
        """
        Instantiate a meta-data object, which expects data from
        n_ants antennas and n_agcs gain control units.
        """
        self.n_ants = n_ants
        self.n_agcs = n_agcs
        self.entries= [
                  {'name':'timestamp', 'form':'!l'},
                  {'name':'obs_status','form':'!i'},
                  {'name':'obs_name',  'form':'!32s'},
                  {'name':'nsamp',     'form':'!i'},
                  {'name':'dummy',     'form':'!i'},
                  {'name':'ra',        'form':'!d'},
                  {'name':'dec',       'form':'!d'},
                  {'name':'ha_reqd',   'form':'!%di'%self.n_ants},
                  {'name':'ha_read',   'form':'!%di'%self.n_ants},
                  {'name':'dec_reqd',  'form':'!%di'%self.n_ants},
                  {'name':'dec_read',  'form':'!%di'%self.n_ants},
                  {'name':'pc_value',  'form':'!%di'%self.n_ants},
                  {'name':'pc_error',  'form':'!%di'%self.n_ants},
                  {'name':'rain_data', 'form':'!%di'%self.n_ants},
                  {'name':'tcryo',     'form':'!%di'%self.n_ants},
                  {'name':'pcryo',     'form':'!%di'%self.n_ants},
                  {'name':'agc',       'form':'!%di'%self.n_agcs},
                 ]
        self.gen_offsets()
        whole_format = '!'
        for entry in self.entries:
            whole_format += entry['form'][1:]
        self.size = struct.calcsize(whole_format)

    def gen_offsets(self):
        """
        Generate the offsets of each value in the meta data struct,
        to allow unpacking later
        """
        offset = 0
        for entry in self.entries:
            entry['offset'] = offset
            offset += struct.calcsize(entry['form'])

    def extract_attr(self,data):
        """
        update the meta_data attributes with the values packed in 'data'
        """
        for entry in self.entries:
            val = struct.unpack_from(entry['form'],data,entry['offset'])
            if len(val) == 1:
                val = val[0]
            if entry['name'] is 'obs_name':
                self.__setattr__(entry['name'],val.split('\x00')[0]) #first part of string upto null byte
            else:
                self.__setattr__(entry['name'],val)

        
class DataStruct(struct.Struct):
    """
    A subclass of Struct to encapsulate correlator data and timestamp
    """
    def __init__(self, n_chans=2048):
        """
        Initialise a data structure for a timestamp, status flag, count number,
        and n_chans oof complex data.
        """
        form = '!lii%dl'%(2*n_chans)
        struct.Struct.__init__(self,form)
