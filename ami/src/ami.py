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
import cPickle as pickle


class AmiDC(object):
    """
    The Ami Digital Correlator class.
    This class provides an interface to the correlator, using a config file
    for hardware set up.
    """
    def __init__(self,config_file=None,verbose=False,passive=True):
        """
        Instantiate a correlator object. Pass a config file for custom configurations,
        otherwise the AMI_DC_CONF environment variable will be used as the config file
        path.
        If passive is True (the default), connections to F/X engines will be initialised,
        and current control software state will be obtained (including sync time),
        but no changes will be made to any hardware set up. If passive is False,
        all FPGAs will be reprogrammed.
        """
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
            self.load_sync()
        else:
            self.program_all()

    def vprint(self,message):
        """
        Print a message is self.verbose is True. To be replaced by logging.
        """
        if self.verbose:
            print message

    def arm_sync(self, send_sync=False):
        """
        Arms all F engines, records anticipated sync time in config file. Returns the UTC time at which
        the system was sync'd in seconds since the Unix epoch (MCNT=0)
        If send_sync = True, a manual software sync will be sent to the F-Engines after arming.
        """
        #wait for within 100ms of a half-second, then send out the arm signal.
        #TODO This code is ripped from medicina. Is it even right?
        ready=0
        while not ready:
            ready=((int(time.time()*10+5)%10)==0)
        self.sync_time=int(time.time())+1
        self.all_fengs('arm_trigger')
        if send_sync:
            # send two syncs, as the first is flushed
            self.all_fengs('man_sync')
            self.all_fengs('man_sync')
        base_dir = os.path.dirname(self.config_file)
        base_name = os.path.basename(self.config_file)
        pkl_file = base_dir + "/sync_" + base_name.split(".xml")[0]+".pkl"
        pickle.dump(self.sync_time, open(pkl_file, "wb"))
        return self.sync_time

    def load_sync(self):
        """Determines if a pickle file with the sync_time exists, returns that value else return 0"""
        base_dir = os.path.dirname(self.config_file)
        base_name = os.path.basename(self.config_file)
        pkl_file = base_dir + "/sync_" + base_name.split(".xml")[0]+".pkl"
        try:
            self.sync_time = pickle.load(open(pkl_file))
        except:
            print "No previous Sync Time found, defaulting to 0 seconds since the Unix Epoch"
            self.sync_time = 0
        return self.sync_time


    def parse_config_file(self):
        """
        Parse the instance's config file, saving some parameters as attributes
        for easy access.
        This method is automatically called on object instantiation.
        """
        self.config = configparser.SafeConfigParser()
        self.config.read(self.config_file)
        #some common params
        self.n_ants  = self.config.getint('correlator_hard','n_ants')
        self.n_bands = self.config.getint('correlator_hard','n_bands')
        self.n_inputs= self.config.getint('correlator_hard','inputs_per_board')
        self.n_chans = self.config.getint('correlator_hard','n_chans')
        self.n_pols = self.config.getint('correlator_hard','n_pols')
        self.output_format = self.config.get('correlator_hard','output_format')
        self.acc_len = self.config.getint('correlator','acc_len')
        self.data_path = self.config.get('correlator','data_path')
        self.roaches = self.config['hardware'].get('roaches').split(',')
        self.adc_clk = self.config.getint('hardware','adc_clk')
        self.lo_freq = self.config.getint('hardware','mix_freq')
        self.n_bls = (self.n_ants * (self.n_ants+1))/2
        #shortcuts to sections
        self.c_testing = self.config['testing']
        self.c_correlator = self.config['correlator']
        self.c_correlator_hard = self.config['correlator_hard']
        self.c_hardware= self.config['hardware']
        #array config file
        self.array_cfile = self.config.get('array','array_layout')
        # some debugging / info
        self.vprint("ROACHes are %r"%self.roaches)


    def connect_to_roaches(self):
        """
        Set up katcp connections to all ROACHes in the correlator config file.
        Add the FpgaClient instances to the self.fpgas list.
        Returns a list of boolean values, corresponding to the connection
        state of each ROACH in the system.
        """
        self.fpgas = []
        for rn,roachhost in enumerate(self.roaches):
            self.vprint("Connecting to ROACH %d, %s"%(rn,roachhost))
            self.fpgas += [Roach(roachhost,boffile=self.c_hardware.get('boffile'))]
        return [fpga.is_connected() for fpga in self.fpgas]

    def initialise_f_engines(self,passive=False):
        """
        Instantiate an FEngine instance for each one specified in the correlator config file.
        Append the FEngine instances to the self.fengs list.
        """
        self.fengs = []
        for roach in self.fpgas:
            for adc in range(self.n_inputs):
                ant  = int(self.config.get(roach.host,'ant').split(',')[adc])
                band = self.config.get(roach.host,'band').split(',')[adc]
                self.fengs.append(FEngine(roach,adc,ant,band,adc_clk=self.adc_clk,lo_freq=self.lo_freq,n_chans=self.n_chans,connect_passively=passive))

    def initialise_x_engines(self,passive=False):
        """
        Instantiate an XEngine instance for each one specified in the correlator config file.
        Append the XEngine instances to the self.xengs list.
        """
        self.xengs = []
        chans_per_roach = self.n_chans / len(self.fpgas)
        for roach in self.fpgas:
            band = self.config.get(roach.host,'xeng_band')
            self.xengs.append(XEngine(roach,'ctrl',band=band,n_ants=self.n_ants,chans=chans_per_roach,connect_passively=passive, acc_len=self.acc_len))

    def all_fengs(self, method, *args, **kwargs):
        """
        Call FEngine method 'method' against all FEngine instances.
        Optional arguments are passed to the FEngine method calls.
        If an attribute rather than a method is specified, the attribute value
        will be returned as a list (one entry for each F-Engine). Otherwise the
        return value is that of the underlying FEngine method call.
        """
        if callable(getattr(FEngine,method)):
            return [getattr(feng, method)(*args, **kwargs) for feng in self.fengs]
        else:
            return [getattr(feng,method) for feng in self.fengs]

    def all_xengs(self, method, *args, **kwargs):
        """
        Call XEngine method 'method' against all XEngine instances.
        Optional arguments are passed to the XEngine method calls.
        If an attribute rather than a method is specified, the attribute value
        will be returned as a list (one entry for each X-Engine). Otherwise the
        return value is that of the underlying XEngine method call.
        """
        if callable(getattr(XEngine,method)):
            return [getattr(xeng,method)(*args, **kwargs) for xeng in self.xengs]
        else:
            return [getattr(xeng,method) for xeng in self.xengs]

    def all_fpgas(self, method, *args, **kwargs):
        """
        Call ROACH method 'method' against all ROACH instances.
        Optional arguments are passed to the ROACH  method calls.
        If an attribute rather than a method is specified, the attribute value
        will be returned as a list (one entry for each ROACH). Otherwise the
        return value is that of the underlying ROACH method call.
        ROACH instances subclass FpgaClient, so you can call any of their methods
        here.
        """
        if callable(getattr(Roach,method)):
            return [getattr(fpga, method)(*args, **kwargs) for fpgas in self.fpgas]
        else:
            return [getattr(fpga,method) for fpga in self.fpgas]

    def program_all(self,reinitialise=True):
        """
        Program all ROACHs. Since F and X engines share boards, programming via this method
        is preferable to programming via the F/XEngine instances.
        By default, F/X instances are rebuild after reprogramming, and FEngine ADCs are recalibrated.
        If reinitialise=False, no engines are instantiated (you will have to call initialise_f/x_engines
        manually.)
        """
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
    def get_array_config(self):
        pass
        

class Roach(katcp.FpgaClient):
    '''
    A minor expansion on the FpgaClient class adds a few methods.
    '''
    def __init__(self, roachhost, port=7147, boffile=None):
        katcp.FpgaClient.__init__(self,roachhost, port)
        self.boffile = boffile
    def snap(self,name,format='L',**kwargs):
        """
        A wrapper for snapshot_get(name, **kwargs), which decodes data into a numpy array, based on the format argument.
        Big endianness is assumped, so only pass the format character. (i.e., 'L' for unsigned 32 bit, etc).
        See the python struct manual for details of available formats.
        """
        n_bytes = struct.calcsize('=%s'%format)
        d = self.snapshot_get(name, **kwargs)
        return np.array(struct.unpack('>%d%s'%(d['length']/n_bytes,format),d['data']))
    def safe_prog(self, check_clock=True):
        """
        A wrapper for the FpgaClient progdev method.
        This method checks the target boffile is available before attempting to program, and clears
        the FPGA before programming. A test write to the sys_scratchpad register is performed after programming.
        If check_clock=True, the FPGA clock rate is estimated via katcp and returned in MHz.
        """
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
        """
        Set the self.boffile attribute, which is used in safe_prog calls.
        """
        self.boffile=boffile
        


class Engine(object):
    """
    A class for F/X engines (or some other kind) which live in ROACH firmware.
    The fundamental assumption is that where multiple engines exist on a ROACH,
    each has a unique prefix/suffix to their register names. (Eg, the registers
    all live in some unique subsystem.
    An engine requires a control register, whose value is tracked by this class
    to enable individual bits to be toggled.
    """
    def __init__(self,roachhost,port=7147,boffile=None,ctrl_reg='ctrl',reg_suffix='',reg_prefix='',connect_passively=True):
        """
        Instantiate an engine which lives on ROACH 'roachhost' who listens on port 'port'.
        All shared memory belonging to this engine has a name beginning with 'reg_prefix'
        and ending in 'reg_suffix'. At least one control register named 'ctrl_reg' (plus pre/suffixes)
        should exist. After configuring these you can write to registers without
        these additions to the register names, allowing multiple engines to live on the same
        ROACH boards transparently.
        If 'connect_passively' is True, the Engine instance will be created and its current control
        software status read, but no changes to the running firmware will be made.
        """
        self.roachhost = roachhost
        self.ctrl_reg = ctrl_reg
        self.reg_suffix = reg_suffix
        self.reg_prefix = reg_prefix
        if connect_passively:
            self.get_ctrl_sw()
        else:
            self.initialise_ctrl_sw()

    def initialise_ctrl_sw(self):
        """Initialises the control software register to zero."""
        self.ctrl_sw=0
        self.write_ctrl_sw()

    def write_ctrl_sw(self):
        """
        Write the current value of the ctrl_sw attribute to the host FPGAs control register
        """
        self.write_int(self.ctrl_reg,self.ctrl_sw)

    def ctrl_sw_edge(self, bit):
        """
        Trigger an edge on a given bit of the control software reg.
        I.e., write 0, then 1, then 0
        """
        self.set_ctrl_sw_bits(bit,bit,0)
        self.set_ctrl_sw_bits(bit,bit,1)
        self.set_ctrl_sw_bits(bit,bit,0)
     
    def set_ctrl_sw_bits(self, lsb, msb, val):
        """
        Set bits lsb:msb of the control register to value 'val'.
        Other bits are maintained by the instance, which tracks the current values of the register.
        """
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
        """
        Updates the ctrl_sw attribute with the current value of the ctrl_sw register.
        Useful when you are instantiating an engine but you don't want to reset
        its control register to zero.
        """
        self.ctrl_sw = self.read_uint(self.ctrl_reg)
        return self.ctrl_sw

    def expand_name(self,name=''):
        """
        Expand a register name with the engines string prefix/suffix
        to distinguish between multiple engines
        on the same roach board
        """
        return self.reg_prefix + name + self.reg_suffix

    def contract_name(self,name=''):
        """
        Strip off the suffix/prefix of a register with a given name.
        Useful if you want to get a list of registers present in an engine
        from a listdev() call to the engines host ROACH.
        """
        return name.rstrip(self.reg_suffix).lstrip(self.reg_prefix)

    def write_int(self, dev_name, integer, *args, **kwargs):
        """
        Write an integer to an engine's register names 'dev_name'.
        This is achieved by calling write_int on the Engine's host ROACH
        after expanding the register name with any suffix/prefix. Optional
        arguments are passed down to the write_int call.
        """
        self.roachhost.write_int(self.expand_name(dev_name), integer, **kwargs)

    def read_int(self, dev_name, *args, **kwargs):
        """
        Read an integer from an engine's register names 'dev_name'.
        This is achieved by calling read_int on the Engine's host ROACH
        after expanding the register name with any suffix/prefix. Optional
        arguments are passed down to the read_int call.
        """
        return self.roachhost.read_int(self.expand_name(dev_name), **kwargs)

    def read_uint(self, dev_name, *args, **kwargs):
        """
        Read an unsigned integer from an engine's register names 'dev_name'.
        This is achieved by calling read_uint on the Engine's host ROACH
        after expanding the register name with any suffix/prefix. Optional
        arguments are passed down to the read_uint call.
        """
        return self.roachhost.read_uint(self.expand_name(dev_name), **kwargs)

    def read(self, dev_name, size, *args, **kwargs):
        """
        Read binary data from an engine's register names 'dev_name'.
        This is achieved by calling read on the Engine's host ROACH
        after expanding the register name with any suffix/prefix. Optional
        arguments are passed down to the read call.
        """
        return self.roachhost.read(self.expand_name(dev_name), size, **kwargs)
        
    def write(self, dev_name, data, *args, **kwargs):
        """
        Read binary data from an engine's register names 'dev_name'.
        This is achieved by calling read on the Engine's host ROACH
        after expanding the register name with any suffix/prefix. Optional
        arguments are passed down to the read call.
        """
        self.roachhost.write(self.expand_name(dev_name), data, **kwargs)
    
    def snap(self, dev_name, **kwargs):
        """
        Call snap on an engine's snap block named 'dev_name'.
        after expanding the register name with any suffix/prefix. Optional
        arguments are passed down to the snap call.
        """
        return self.roachhost.snap(self.expand_name(dev_name), **kwargs)

    def snapshot_get(self, dev_name, **kwargs):
        """
        Call snapshot_get on an engine's snap block named 'dev_name'.
        after expanding the register name with any suffix/prefix. Optional
        arguments are passed down to the snapshot_get call.
        """
        return self.roachhost.snapshot_get(self.expand_name(dev_name), **kwargs)

    def listdev(self):
        """
        Return a list of registers associated with an Engine instance.
        This is achieved by calling listdev() on the Engine's host ROACH,
        and then stripping off prefix/suffixes which are unique to this
        particular engine instance.
        """
        dev_list = self.roachhost.listdev()
        dev_list.sort() #alphebetize
        #find the valid devices, which are those which start with the prefix and end with the suffix
        valid_list = []
        for dev in dev_list:
            if dev.startswith(self.reg_prefix) and dev.endswith(self.reg_suffix):
                valid_list.append(self.contract_name(dev))
        return valid_list

class FEngine(Engine):
    """
    A subclass of Engine, encapsulating F-Engine specific properties.
    """
    def __init__(self,roachhost,adc,ant,band,n_chans=1024,adc_clk=4000.,lo_freq=0.,ctrl_reg='ctrl',connect_passively=True):
        """
        Instantiate an F-Engine.
        adc: An integer, refering to the ADC (ZDOK) number associated with this engine.
        ant: The antenna number processed by this engine.
        band: 'low' or 'high' -- The sideband processed by this engine
        n_chans: The number of channels this engine generates
        adc_clk: The ADC sample clock (in MHz)
        lo_freq: The mixing frequency of any LO prior to this engines ADC
        ctrl_reg: The name of the control register of this engine
        connect_passively: True if you want to instantiate an engine without modifying it's
        current running state. False if you want to reinitialise the control software of this engine.
        """
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
        """
        Write the fft_shift value for this engine
        """
        self.write_int('fft_shift',shift)
    def gen_freq_scale(self):
        """
        Generate the frequency scale corresponding fo the frequencies of each
        channel produced by this engine (in the order they emerge from the engine's
        FFT. Useful for plotting.
        """
        band = np.arange(0,self.adc_clk/2.,self.adc_clk/2./self.n_chans)
        if self.band == 'low':
           rf_band = self.lo_freq - band
        else:
           rf_band = self.lo_freq + band
        return rf_band
    def set_EQ():
        """
        Set the engine EQ coefficients
        """
        raise NotImplementedError
    def set_coarse_delay(self,delay):
        """
        Set the engine's coarse delay (in FPGA clock cycles)
        """
        self.write_int('coarse_delay',delay)
    def reset(self):
        """
        reset the engine using the control register
        """
        self.ctrl_sw_edge(0)
    def man_sync(self):
        """
        Send a manual sync to the engine using the control register
        """
        self.ctrl_sw_edge(1)
    def arm_trigger(self):
        """
        Arm the sync generator using the control register
        """
        self.ctrl_sw_edge(2)
    def clr_status(self):
        """
        Clear the status flags, using the control register
        """
        self.ctrl_sw_edge(3)
    def clr_adc_bad(self):
        """
        Clear the adc clock bad flag, using the control register
        """
        self.ctrl_sw_edge(4)
    def gbe_rst(self):
        """
        Reset the engine's 10GbE outputs, using the control register
        """
        self.ctrl_sw_edge(8)
    def gbe_enable(self,val):
        """
        Set the engine's 10GbE output enable state to bool(val), using the control regiser
        """
        self.set_ctrl_sw_bits(9,9,int(val))
    def fancy_en(self,val):
        """
        Set the fancy led enable mode to bool(val)
        """
        self.set_ctrl_sw_bits(12,12,int(val))
    def adc_protect_disable(self,val):
        """
        Turn off adc protection if val=True. Else turn on.
        """
        self.set_ctrl_sw_bits(13,13,int(val))
    def tvg_en(self,corner_turn=False,packetiser=False,fd_fs=False,adc=False):
        """
        Turn on any test vector generators whose values are 'True'
        Turn off any test vector generators whose values are 'False'
        """
        self.set_ctrl_sw_bits(17,17,int(corner_turn))
        self.set_ctrl_sw_bits(18,18,int(packetiser))
        self.set_ctrl_sw_bits(19,19,int(fd_fs))
        self.set_ctrl_sw_bits(20,20,int(adc))
        self.ctrl_sw_edge(16)
    def phase_switch_enable(self,val):
        """
        Set the phase switch enable state to bool(val)
        """
        self.set_ctrl_sw_bits(21,21,int(val))
    def set_tge_outputs():
        """
        Configure engine's 10GbE outputs.
        Not yet implemented
        """
        raise NotImplementedError()
    def get_status(self):
        """
        return the status flags defined in the def_fstatus file
        """
        val = self.read_int('status')
        rv = {}
        for key in def_fstatus.status.keys():
            item = def_fstatus.status[key]
            rv[key] = helpers.slice(val,item['start_bit'],width=item['width'])
        return rv
    def print_status(self):
        """
        Print the status flags defined in the def_fstatus file, highlighting
        and 'bad' flags.
        """
        print "STATUS of F-Engine %d (Antenna %d %s band) on ROACH %s"%(self.adc,self.ant,self.band,self.roachhost.host)
        vals = self.get_status()
        for key in vals.keys():
            if vals[key] == def_fstatus.status[key]['default']:
                print colored('%15s : %r'%(key,vals[key]), 'green')
            else:
                print colored('%15s : %r'%(key,vals[key]), 'red', attrs=['bold'])


    def calibrate_adc(self,verbosity=1):
        """
        Calibrate the ADC associated with this engine, using the adc5g.calibrate_mmcm_phase method.
        """
        adc.calibrate_all_delays(self.roachhost,self.adc,snaps=[self.expand_name('snapshot_adc')],verbosity=2)
        opt,glitches =  adc.calibrate_mmcm_phase(self.roachhost,self.adc,[self.expand_name('snapshot_adc')])
        print opt
        print glitches


class XEngine(Engine):
    """
    A subclass of Engine, encapsulating X-Engine specific properties
    """
    def __init__(self,roachhost,ctrl_reg='ctrl',id=0,band='low',chans=1024,n_ants=8, acc_len=1024, connect_passively=True):
        """
        Instantiate a new X-engine.
        roachhost: The hostname of the ROACH on which this Engine lives
        ctrl_reg: The name of the control register of this engine
        id: The id of this engine, if multiple are present on a ROACH
        chans: The number of channels processed by this X-engine
        n_ants: The number of antennas processed by this X-engine
        acc_len: The accumulation length of this X-engine
        connect_passively: True if you want to instantiate an engine without modifying it's
        current running state. False if you want to reinitialise the control software of this engine.
        """
        Engine.__init__(self,roachhost,ctrl_reg=ctrl_reg,connect_passively=connect_passively,reg_prefix='xeng_')
        self.id = id
        self.chans=1024
        self.n_ants = n_ants
        self.acc_len = acc_len
        self.band = band
        if not connect_passively:
            self.set_acc_len()

    def reset():
        """
        Reset this engine
        """
        pass
    def set_acc_len(self,acc_len=None):
        """
        Set the accumulation length of this engine, using either the
        current value of the acc_len attribute, or a new value if supplied
        """
        if acc_len is not None:
            self.acc_len = acc_len
        self.write_int('acc_len',self.acc_len)
        pass
    def set_output_addr():
        """
        Set address of output data stream
        """
        pass
    def set_tge_inputs():
        """
        Configure input 10GbE data streams
        """
        pass

class AmiSbl(AmiDC):
    """
    A subclass of AmiDC for the single-ROACH, single-baseline correlator
    """
    def __init__(self,config_file=None,verbose=False,passive=True):
        """
        Instantiate a correlator object. Pass a config file for custom configurations,
        otherwise the AMI_DC_CONF environment variable will be used as the config file
        path.
        If passive is True (the default), connections to F/X engines will be initialised,
        and current control software state will be obtained (including sync time),
        but no changes will be made to any hardware set up. If passive is False,
        all FPGAs will be reprogrammed.
        """
        AmiDC.__init__(self,config_file=config_file,verbose=verbose,passive=passive)
    def snap_corr(self,wait=True,combine_complex=True):
        """
        Snap new correlations from bram.
        If wait is True, this method will return the correlations when they are ready,
        and block until this happens. Otherwise, the current values will be returned,
        whether or not this is a new accumulation.
        If combine_complex is true, complex data is returned as a complex number array.
        Otherwise, complex data is returned as a real array who's even and odd elements
        represent the imaginary and real correlation parts.
        The current accumulation number (MCNT) is read before and after reading data,
        if this changes during the read, nothing is returned.
        If the read is successful, the returned data is a dictionary with keys:
            corr00
            corr11
            corr01
            timestamp
        """
        if str(self.output_format) == 'q':
            array_fmt = np.int64
        elif str(self.output_format) == 'l':
            array_fmt = np.int32

        xeng0 = self.xengs[0]
        if wait:
            mcnt = xeng0.read_int('mcnt_lsb')
            #sleep until there's a new correlation
            while xeng0.read_int('mcnt_lsb') == mcnt:
                time.sleep(0.01)

        snap00 = np.zeros(self.n_chans*self.n_bands,dtype=array_fmt)
        snap11 = np.zeros(self.n_chans*self.n_bands,dtype=array_fmt)
        snap01 = np.zeros(2*self.n_chans*self.n_bands,dtype=array_fmt)

        for xn,xeng in enumerate(self.xengs):
            mcnt_msb = xeng.read_uint('mcnt_msb')
            mcnt_lsb = xeng.read_uint('mcnt_lsb')
            mcnt = (mcnt_msb << 32) + mcnt_lsb
            pack_format = '>%d%s'%(self.n_chans,str(self.output_format))
            c_pack_format = '>%d%s'%(2*self.n_chans,str(self.output_format))
            n_bytes = struct.calcsize(pack_format)
            if xeng.band == 'low':
                snap00[0:self.n_chans]   = np.array(struct.unpack(pack_format,xeng.read('corr00_bram',n_bytes)))
                snap11[0:self.n_chans]   = np.array(struct.unpack(pack_format,xeng.read('corr11_bram',n_bytes)))
                snap01[0:2*self.n_chans]   = np.array(struct.unpack(c_pack_format,xeng.read('corr01_bram',2*n_bytes)))
            else:
                snap00[(self.n_bands-1)*self.n_chans:self.n_bands*self.n_chans]   = np.array(struct.unpack(pack_format,xeng.read('corr00_bram',n_bytes)))[::-1]
                snap11[(self.n_bands-1)*self.n_chans:self.n_bands*self.n_chans]   = np.array(struct.unpack(pack_format,xeng.read('corr11_bram',n_bytes)))[::-1]
                snap01[2*(self.n_bands-1)*self.n_chans:2*self.n_bands*self.n_chans]   = np.array(struct.unpack(c_pack_format,xeng.read('corr01_bram',2*n_bytes)))[::-1]
            #snap01c   = np.array(snap01[1::2] + 1j*snap01[0::2], dtype=complex)
            #snap00   = np.zeros(self.n_chans)
            #snap11   = np.zeros(self.n_chans)
            #snap01   = np.zeros(2*self.n_chans)
            if mcnt_lsb != xeng.read_uint('mcnt_lsb'):
                print mcnt_lsb, xeng.read_uint('mcnt_lsb')
                print "SNAP CORR: mcnt changed before snap completed!"
                return None

        if combine_complex:
            snap01   = np.array(snap01[0::2] + 1j*snap01[1::2], dtype=complex)
        return {'corr00':snap00,'corr11':snap11,'corr01':snap01,'timestamp':self.mcnt2time(mcnt)}
    def mcnt2time(self,mcnt):
        """
        Convert an mcnt to a UTC time based on the instance's sync_time attribute.
        """
        conv_factor = 16./(self.adc_clk*1e6)
        offset = self.sync_time
        return offset + mcnt*conv_factor
