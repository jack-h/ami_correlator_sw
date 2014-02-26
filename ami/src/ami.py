import os
import corr.katcp_wrapper as katcp
import adc5g as adc
import numpy as np
import time
import struct
import configparser
from termcolor import colored
import helpers
import def_fstatus

class AmiDC(object):
    def __init__(self,config_file=None,verbose=False,passive=True):
        self.verbose = verbose
        if config_file is None:
            self.config_file = os.environ.get('AMI_DC_CONF')
            if self.config_file is None:
                raise ValueError("No config file given, and no AMI_DC_CONF variable!")
        else:
            self.config_file = config_file
        self.vprint("Building AmiDC with config file %s"%self.config_file)
        self.vprint("parsing config file")
        self.parse_config_file()
        self.vprint("connecting to roaches")
        self.connect_to_roaches()
        time.sleep(0.1)
        if passive:
            self.vprint("Initialising ROACHes passively")
            self.initialise_f_engines(passive=passive)
            self.initialise_x_engines(passive=passive)
        else:
            self.program_all()

    def vprint(self,message):
        if self.verbose:
            print message

    def parse_config_file(self):
        self.config = configparser.SafeConfigParser()
        self.config.read(self.config_file)
        #some common params
        self.n_ants  = self.config.getint('correlator_hard','n_ants')
        self.n_bands = self.config.getint('correlator_hard','n_bands')
        self.n_inputs= self.config.getint('correlator_hard','inputs_per_board')
        self.n_chans = self.config.getint('correlator_hard','n_chans')
        self.acc_len = self.config.getint('correlator','acc_len')
        self.roaches = self.config['hardware'].get('roaches').split(',')
        self.adc_clk = self.config.getint('hardware','adc_clk')
        self.lo_freq = self.config.getint('hardware','mix_freq')
        #shortcuts to sections
        self.c_testing = self.config['testing']
        self.c_correlator = self.config['correlator']
        self.c_correlator_hard = self.config['correlator_hard']
        self.c_hardware= self.config['hardware']
        # some debugging / info
        self.vprint("ROACHes are %r"%self.roaches)


    def connect_to_roaches(self):
        self.fpgas = []
        for rn,roachhost in enumerate(self.roaches):
            self.vprint("Connecting to ROACH %d, %s"%(rn,roachhost))
            self.fpgas += [Roach(roachhost,boffile=self.c_hardware.get('boffile'))]
        return [fpga.is_connected() for fpga in self.fpgas]

    def initialise_f_engines(self,passive=False):
        self.fengs = []
        for roach in self.fpgas:
            for adc in range(self.n_inputs):
                ant  = int(self.config.get(roach.host,'ant').split(',')[adc])
                band = self.config.get(roach.host,'band').split(',')[adc]
                self.fengs.append(FEngine(roach,adc,ant,band,adc_clk=self.adc_clk,lo_freq=self.lo_freq,n_chans=self.n_chans,connect_passively=passive))

    def initialise_x_engines(self,passive=False):
        self.xengs = []
        chans_per_roach = self.n_chans / len(self.fpgas)
        for roach in self.fpgas:
            self.xengs.append(XEngine(roach,'ctrl',n_ants=self.n_ants,chans=chans_per_roach,connect_passively=passive, acc_len=self.acc_len))

    def all_fengs(self, method, *args, **kwargs):
        if callable(getattr(FEngine,method)):
            return [getattr(feng, method)(*args, **kwargs) for feng in self.fengs]
        else:
            return [getattr(feng,method) for feng in self.fengs]

    def all_xengs(self, method, *args, **kwargs):
        if callable(getattr(XEngine,method)):
            return [getattr(xeng,method)(*args, **kwargs) for xeng in self.xengs]
        else:
            return [getattr(xeng,method) for xeng in self.xengs]

    def all_fpgas(self, method, *args, **kwargs):
        if callable(getattr(Roach,method)):
            return [getattr(fpga, method)(*args, **kwargs) for fpgas in self.fpgas]
        else:
            return [getattr(fpga,method) for fpga in self.fpgas]

    def program_all(self,reinitialise=True):
        for roach in self.fpgas:
            self.vprint("Programming ROACH %s with boffile %s"%(roach.host,roach.boffile))
            roach.safe_prog()
        if reinitialise:
            # reprogramming messes with ctrl_sw, etc, so clean out the engine lists
            self.initialise_f_engines(passive=False)
            self.initialise_x_engines(passive=False)
        else:
            self.fengs = []
            self.xengs = []
        for fn,feng in enumerate(self.fengs):
            feng.calibrate_adc(verbosity=int(self.verbose))

class Roach(katcp.FpgaClient):
    '''
    A minor expansion on the FpgaClient class adds a few methods.
    '''
    def __init__(self, roachhost, port=7147, boffile=None):
        katcp.FpgaClient.__init__(self,roachhost, port)
        self.boffile = boffile
    def snap(self,name,format='L',**kwargs):
        n_bytes = struct.calcsize('=%s'%format)
        d = self.snapshot_get(name, **kwargs)
        return np.array(struct.unpack('>%d%s'%(d['length']/n_bytes,format),d['data']))
    def safe_prog(self, check_clock=True):
        if self.boffile not in self.listbof():
            raise RuntimeError("boffile %s not available on ROACH %s"%(self.boffile,self.host))
        self.progdev('')
        time.sleep(0.1)
        self.progdev(self.boffile)
        time.sleep(0.1)
        # write_int automatically does a read check. The following call will fail
        # if the roach hasn't programmed properly
        self.write_int('sys_scratchpad',0xdeadbeef)
        if check_clock:
            return self.est_brd_clk()
        else:
            return None
    def set_boffile(self,boffile):
        self.boffile=boffile
        


class Engine(object):
    def __init__(self,roachhost,port=7147,boffile=None,ctrl_reg='ctrl',reg_suffix='',reg_prefix='',connect_passively=True):
        self.roachhost = roachhost
        self.ctrl_reg = ctrl_reg
        self.reg_suffix = reg_suffix
        self.reg_prefix = reg_prefix
        if connect_passively:
            self.initialise_ctrl_sw()
        else:
            self.get_ctrl_sw()

    def initialise_ctrl_sw(self):
        """Initialises the control software register to zero."""
        self.ctrl_sw=0
        self.write_ctrl_sw()

    def write_ctrl_sw(self):
        self.write_int(self.ctrl_reg,self.ctrl_sw)

    def ctrl_sw_edge(self, bit):
        '''
        Trigger an edge on a given bit of the control software reg.
        I.e., write 0, then 1, then 0
        '''
        self.set_ctrl_sw_bits(bit,bit,0)
        self.set_ctrl_sw_bits(bit,bit,1)
        self.set_ctrl_sw_bits(bit,bit,0)
     
    def set_ctrl_sw_bits(self, lsb, msb, val):
        num_bits = msb-lsb+1
        if val > (2**num_bits - 1):
            print 'ctrl_sw MSB:', msb
            print 'ctrl_sw LSB:', lsb
            print 'ctrl_sw Value:', val
            raise ValueError("ERROR: Attempting to write value to ctrl_sw which exceeds available bit width")
        # Create a mask which has value 0 over the bits to be changed                                     
        mask = (2**32-1) - ((2**num_bits - 1) << lsb)
        # Remove the current value stored in the ctrl_sw bits to be changed
        self.ctrl_sw = self.ctrl_sw & mask
        # Insert the new value
        self.ctrl_sw = self.ctrl_sw + (val << lsb)
        # Write                                                                                           
        self.write_ctrl_sw()
        
    def get_ctrl_sw(self):
        """Updates the ctrl_sw attribute with the current value of the ctrl_sw register"""
        self.ctrl_sw = self.read_uint(self.ctrl_reg)
        return self.ctrl_sw

    def expand_name(self,name=''):
        '''
        Expand a register name with a string suffix
        to distinguish between multiple engines
        on the same roach board
        '''
        return self.reg_prefix + name + self.reg_suffix

    def contract_name(self,name=''):
        return name.rstrip(self.reg_suffix).lstrip(self.reg_prefix)

    def write_int(self, dev_name, integer, *args, **kwargs):
        self.roachhost.write_int(self.expand_name(dev_name), integer, **kwargs)

    def read_int(self, dev_name, *args, **kwargs):
        return self.roachhost.read_int(self.expand_name(dev_name), **kwargs)

    def read_uint(self, dev_name, *args, **kwargs):
        return self.roachhost.read_uint(self.expand_name(dev_name), **kwargs)

    def read(self, dev_name, size, *args, **kwargs):
        self.roachhost.read(self.expand_name(dev_name), size, **kwargs)
        
    def write(self, dev_name, data, *args, **kwargs):
        self.roachhost.write(self.expand_name(dev_name), data, **kwargs)
    
    def snap(self, dev_name, **kwargs):
        return self.roachhost.snap(self.expand_name(dev_name), **kwargs)

    def snapshot_get(self, dev_name, **kwargs):
        return self.roachhost.snapshot_get(self.expand_name(dev_name), **kwargs)

    def listdev(self):
        dev_list = self.roachhost.listdev()
        dev_list.sort() #alphebetize
        #find the valid devices, which are those which start with the prefix and end with the suffix
        valid_list = []
        for dev in dev_list:
            if dev.startswith(self.reg_prefix) and dev.endswith(self.reg_suffix):
                valid_list.append(self.contract_name(dev))
        return valid_list

class FEngine(Engine):
    def __init__(self,roachhost,adc,ant,band,n_chans=1024,adc_clk=4000.,lo_freq=0.,ctrl_reg='ctrl',connect_passively=True):
        self.adc = adc
        self.adc_clk = adc_clk
        self.lo_freq = lo_freq
        self.ant = ant
        self.band = band
        self.n_chans = n_chans
        if self.band == 'low':
            self.inv_band = True
        elif self.band == 'high':
            self.inv_band = False
        else:
            raise ValueError('FEngine Error: band can only have values "low" or "high"')
        Engine.__init__(self,roachhost,ctrl_reg=ctrl_reg, reg_prefix='feng_', reg_suffix=str(self.adc), connect_passively=connect_passively)

    def set_fft_shift(self,shift):
        self.write_int('fft_shift',shift)
    def gen_freq_scale(self):
        band = np.arange(0,self.adc_clk/2.,self.adc_clk/2./self.n_chans)
        if self.band == 'low':
           rf_band = self.lo_freq - band
        else:
           rf_band = self.lo_freq + band
        return rf_band
    def set_EQ():
        raise NotImplementedError
    def set_coarse_delay(self,delay):
        self.write_int('coarse_delay',delay)
    def reset(self):
        self.ctrl_sw_edge(0)
    def man_sync(self):
        self.ctrl_sw_edge(1)
    def arm_trigger(self):
        self.ctrl_sw_edge(2)
    def clr_status(self):
        self.ctrl_sw_edge(3)
    def clr_adc_bad(self):
        self.ctrl_sw_edge(4)
    def gbe_rst(self):
        self.ctrl_sw_edge(8)
    def gbe_enable(self,val):
        self.set_ctrl_sw_bits(9,9,int(val))
    def fancy_en(self,val):
        self.set_ctrl_sw_bits(12,12,int(val))
    def adc_protect_disable(self,val):
        self.set_ctrl_sw_bits(13,13,int(val))
    def tvg_en(self,corner_turn=False,packetiser=False,fd_fs=False,adc=False):
        self.set_ctrl_sw_bits(17,17,int(corner_turn))
        self.set_ctrl_sw_bits(18,18,int(packetiser))
        self.set_ctrl_sw_bits(19,19,int(fd_fs))
        self.set_ctrl_sw_bits(20,20,int(adc))
        self.ctrl_sw_edge(16)
    def phase_switch_enable(self,val):
        self.set_ctrl_sw_bits(21,21,int(val))
    def set_tge_outputs():
        raise NotImplementedError()
    def get_status(self):
        val = self.read_int('status')
        rv = {}
        for key in def_fstatus.status.keys():
            item = def_fstatus.status[key]
            rv[key] = helpers.slice(val,item['start_bit'],width=item['width'])
        return rv
    def print_status(self):
        print "STATUS of F-Engine %d (Antenna %d %s band) on ROACH %s"%(self.adc,self.ant,self.band,self.roachhost.host)
        vals = self.get_status()
        for key in vals.keys():
            if vals[key] == def_fstatus.status[key]['default']:
                print colored('%15s : %r'%(key,vals[key]), 'green')
            else:
                print colored('%15s : %r'%(key,vals[key]), 'red', attrs=['bold'])


    def calibrate_adc(self,verbosity=1):
        #adc.calibrate_all_delays(self.roachhost,self.adc,snaps=[self.expand_name('snapshot_adc')],verbosity=2)
        opt,glitches =  adc.calibrate_mmcm_phase(self.roachhost,self.adc,[self.expand_name('snapshot_adc')])
        print opt
        print glitches


class XEngine(Engine):
    def __init__(self,roachhost,ctrl_reg='ctrl',id=0,chans=1024,n_ants=8, acc_len=1024, connect_passively=True):
        Engine.__init__(self,roachhost,ctrl_reg=ctrl_reg,connect_passively=connect_passively,reg_prefix='xeng_')
        self.id = id
        self.chans=1024
        self.n_ants = n_ants
        self.acc_len = acc_len
        if not connect_passively:
            self.set_acc_len()

    def reset():
        pass
    def set_acc_len(self,acc_len=None):
        if acc_len is not None:
            self.acc_len = acc_len
        self.write_int('acc_len',self.acc_len)
        pass
    def set_output_addr():
        pass
    def set_tge_inputs():
        pass


  

