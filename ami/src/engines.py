import helpers
from termcolor import colored
import def_fstatus
import time, struct, logging
import adc5g as adc
import roach

logger = helpers.add_default_log_handlers(logging.getLogger(__name__))

class Engine(object):
    """
    A class for F/X engines (or some other kind) which live in ROACH firmware.
    The fundamental assumption is that where multiple engines exist on a ROACH,
    each has a unique prefix/suffix to their register names. (Eg, the registers
    all live in some unique subsystem.
    An engine requires a control register, whose value is tracked by this class
    to enable individual bits to be toggled.
    """
    def __init__(self,roachhost,port=7147,boffile=None,ctrl_reg='ctrl',reg_suffix='',reg_prefix='',connect_passively=True,num=0,logger=logger):
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
        self._logger = logger
        hostname = roachhost.host
        self.roachhost = roach.Roach(hostname, port)
        time.sleep(0.01)
        self.ctrl_reg = ctrl_reg
        self.reg_suffix = reg_suffix
        self.reg_prefix = reg_prefix
        self.num = num
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
    def __init__(self, roachhost, ctrl_reg='ctrl', connect_passively=False, num=0, **kwargs):
        """
        Instantiate an F-Engine.
        roachhost: A katcp FpgaClient object for the host on which this engine is instantiated
        ctrl_reg: The name of the control register of this engine
        connect_passively: True if you want to instantiate an engine without modifying it's
        current running state. False if you want to reinitialise the control software of this engine.
        config: A dictionary of parameters for this fengine
        """
        # attributize dictionary
        for key in kwargs.keys():
            self.__setattr__(key, kwargs[key])

        if self.band == 'low':
            self.inv_band = True
        elif self.band == 'high':
            self.inv_band = False
        else:
            raise ValueError('FEngine Error: band can only have values "low" or "high"')
        Engine.__init__(self,roachhost,ctrl_reg=ctrl_reg, reg_prefix='feng%s_'%str(self.adc), reg_suffix='', connect_passively=connect_passively, num=num)
        #Engine.__init__(self,roachhost,ctrl_reg=ctrl_reg, reg_prefix='feng_', reg_suffix=str(self.adc), connect_passively=connect_passively)
        # set the default noise seed
        if not connect_passively:
            self.set_adc_noise_tvg_seed()
            self.phase_switch_enable(self.phase_switch)
            self.noise_switch_enable(True)
            self.set_adc_acc_len()
            self.set_fft_acc_len()

    def config_get(self, key):
        if key in self.config.keys():
            return self.config[key]
        elif key in self.global_config.keys():
            return self.global_config[key]
        else:
            raise KeyError('Key %s not in local or global configs!'%key)

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
    def set_adc_noise_tvg_seed(self, seed=0xdeadbeef):
        """
        Set the seed for the adc test vector generator.
        Default is 0xdeadbeef.
        """
        self.write_int('noise_seed', seed)
    def phase_switch_enable(self,val):
        """
        Set the phase switch enable state to bool(val)
        """
        self.set_ctrl_sw_bits(21,21,int(val))
    def noise_switch_enable(self, val):
        """
        Enable or disable the noise switching circuitry
        """
        self.set_ctrl_sw_bits(22,22,int(val))
    def set_adc_acc_len(self, val=None):
        if val is None:
            self.write_int('adc_acc_len', self.adc_power_acc_len >> (4 + 8))
        else:
            self.write_int('adc_acc_len', val >> (4 + 8))
    def set_fft_acc_len(self, val=None):
        if 'auto_acc_len' in self.listdev():
            if val is None:
                self.write_int('auto_acc_len', self.fft_power_acc_len)
            else:
                self.write_int('auto_acc_len', val)
        else:
            if val is None:
                self.write_int('auto_acc_len1', self.fft_power_acc_len)
            else:
                self.write_int('auto_acc_len1', val)
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


    def calibrate_adc(self):
        """
        Calibrate the ADC associated with this engine, using the adc5g.calibrate_mmcm_phase method.
        """
        # The phase switches must be off for calibration
        self.phase_switch_enable(0)
        self._logger.info('Calibrating ADC link')
        adc.calibrate_all_delays(self.roachhost,self.adc,snaps=[self.expand_name('snapshot_adc')])
        # Set back to user-defined defaults
        self.phase_switch_enable(self.phase_switch)
        #opt,glitches =  adc.calibrate_mmcm_phase(self.roachhost,self.adc,[self.expand_name('snapshot_adc')])
        #print opt
        #print glitches
    def get_adc_power(self):
        init_val = self.read_int('adc_sum_sq0')
        while (True):
            v = self.read_int('adc_sum_sq0')
            #print v
            if v != init_val:
                break
            time.sleep(0.01)
        v += (self.read_int('adc_sum_sq1') << 32)
        if v > (2**63 - 1):
            v -= 2**64
        return v / (2**7 * 256.0 * 16.0 * (self.adc_power_acc_len >> (4 + 8)))

    def get_spectra(self, autoflip=False):
        d = np.zeros(self.n_chans)
        # arm snap blocks
        # WARNING: we can't gaurantee that they all trigger off the same pulse
        for i in range(4):
            self.write_int('auto_snap_%d_ctrl'%i,0)
        for i in range(4):
            self.write_int('auto_snap_%d_ctrl'%i,1)

        # wait for data to come.
        # NB: there is no timeout condition
        done = False
        while not done:
            status = self.read_int('auto_snap_0_status')
            done = not bool(status & (1<<31))
            nbytes = status & (2**31 - 1)
            time.sleep(0.01)

        # grab data
        for i in range(4):
            s = np.array(struct.unpack('>%dq'%(nbytes/8), self.read('auto_snap_%d_bram'%i, nbytes)))
            #s = self.snap('auto_snap_%d'%i, format='q')
            d[2*i::8] = s[0::2]
            d[2*i + 1::8] = s[1::2]

        d /= float(self.fft_power_acc_len)
        d /= 2**34
        if autoflip and (self.band == 'high'):
            d = d[::-1]

        return d



class XEngine(Engine):
    """
    A subclass of Engine, encapsulating X-Engine specific properties
    """
    def __init__(self,roachhost,ctrl_reg='ctrl',id=0,band='low',chans=1024,n_ants=8, acc_len=1024, connect_passively=True, num=0):
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
        Engine.__init__(self,roachhost,ctrl_reg=ctrl_reg,connect_passively=connect_passively,reg_prefix='xeng_', num=num)
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
