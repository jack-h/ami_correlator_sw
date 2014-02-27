import os
import h5py
import configparser

class H5Writer(object):
    def __init__(self,config_file=None,band='low'):
        if config_file is None:
            self.config_file = os.environ.get('AMI_DC_CONF')
            if self.config_file is None:
                raise ValueError("No config file given, and no AMI_DC_CONF variable!")
        else:
            self.config_file = config_file
        self.band = band
        self.parse_config_file()
        self.datasets = {}
        self.datasets_index = {}
        self.fh=None
    def parse_config_file(self):
        self.config = configparser.SafeConfigParser()
        self.config.read(self.config_file)
        #some common params
        self.n_ants  = self.config.getint('correlator_hard','n_ants')
        self.n_pols  = self.config.getint('correlator_hard','n_pols')
        self.n_bands = self.config.getint('correlator_hard','n_bands')
        self.n_inputs= self.config.getint('correlator_hard','inputs_per_board')
        self.n_chans = self.config.getint('correlator_hard','n_chans')
        self.output_format = self.config.get('correlator_hard','output_format')
        self.acc_len = self.config.getint('correlator','acc_len')
        self.data_path = self.config.get('correlator','data_path')
        self.roaches = self.config['hardware'].get('roaches').split(',')
        self.adc_clk = self.config.getint('hardware','adc_clk')
        self.lo_freq = self.config.getint('hardware','mix_freq')
        self.n_bls = (self.n_ants * (self.n_ants+1))/2
        if self.band == 'low':
            self.center_freq = self.lo_freq - self.adc_clk/4.
        elif self.band == 'high':
            self.center_freq = self.lo_freq + self.adc_clk/4.
        self.bandwidth = self.adc_clk/2.
        #shortcuts to sections
        self.c_testing = self.config['testing']
        self.c_correlator = self.config['correlator']
        self.c_correlator_hard = self.config['correlator_hard']
        self.c_hardware= self.config['hardware']
    def start_new_file(self,name):
        # close old file if necessary
        if self.fh is not None:
            self.close_file()
        self.fh = h5py.File(self.data_path+'/'+name,'w')
        self.write_fixed_attributes()
        self.datasets = {}
        self.datasets_index = {}
    def set_bl_order(self,order):
        self.bl_order = order
    def write_fixed_attributes(self):
        self.fh.attrs['n_chans'] = self.n_chans
        self.fh.attrs['n_pols'] = self.n_pols
        self.fh.attrs['n_bls'] = self.n_bls
        self.fh.attrs['n_ants'] = self.n_ants
        self.fh.create_dataset('bl_order',shape=[self.n_bls,2],dtype=int,data=self.bl_order)
        self.fh.attrs['center_freq'] = self.center_freq
        self.fh.attrs['bandwidth'] = self.bandwidth
    def add_new_dataset(self,name,shape,data):
        self.fh.create_dataset(name,[1] + ([] if list(shape) == [1] else list(shape)), maxshape=[None] + ([] if list(shape) == [1] else list(shape)))
        self.datasets[name] = name
        self.datasets_index[name] = 0
    def append_data(self,name,shape,data):
        if name not in self.datasets.keys():
            self.add_new_dataset(name,shape,data)
        else:
            self.fh[name].resize(self.datasets_index[name]+1,axis=0)
        self.fh[name][self.datasets_index[name]] = data
        self.datasets_index[name] += 1
    def close_file(self):
        if self.fh is not None:
            self.fh.close()
        self.fh = None
    def add_attr(self,name,val):
        self.fh.attrs[name] = val
