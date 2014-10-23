import os
import numpy as np
import time
import struct
import yaml
import helpers
import redis
import config_redis
import threading
import Queue
import logging
import roach
import engines
import antenna_functions
from corr import sim

logger = helpers.add_default_log_handlers(logging.getLogger(__name__))

def _queue_instance_method(q, num, inst, method, args, kwargs):
    '''
    Add an [num, inst.method(*args, **kwargs)] call to queue, q.
    Use q.get() to get the return data from this call.
    
    This function is used for parallelizing calls to multiple
    roaches/engines.
    '''
    q.put([num, getattr(inst, method)(*args, **kwargs)])


class AmiDC(object):
    """
    The Ami Digital Correlator class.
    This class provides an interface to the correlator, using a config file
    for hardware set up.
    """
    def __init__(self, config_file=None, passive=True, skip_prog=True, logger=logger):
        """
        Instantiate a correlator object. Pass a config file for custom configurations,
        otherwise the AMI_DC_CONF environment variable will be used as the config file
        path.
        If passive is True (the default), connections to F/X engines will be initialised,
        and current control software state will be obtained (including sync time),
        but no changes will be made to any hardware set up. If passive is False,
        all FPGAs will be reprogrammed.
        """
        self._logger = logger

        self.redis_host = config_redis.JsonRedis('ami_redis_host')
        if config_file is None:
            self.config = yaml.load(self.redis_host.hget('config', 'conf'))
            host = self.redis_host.hget('config', 'host')
            fn = self.redis_host.hget('config', 'file')
            config_file = '%s:%s'%(host, fn)
        else:
            self.config = yaml.load(config_file)

        self._logger.info("Building AmiDC with config file %s"%config_file)
        self._logger.info("parsing config file")
        self.parse_config_file()
        self._logger.info("connecting to roaches")
        self.connect_to_roaches()
        time.sleep(0.1)

        if passive:
            self.initialise_f_engines(passive=True)
            self.initialise_x_engines(passive=True)
            self.load_sync()
        elif skip_prog:
            self.initialise_f_engines(passive=False)
            self.initialise_x_engines(passive=False)
            self.load_sync()
        else:
            self.program_all()

    def arm_sync(self, send_sync=False):
        """
        Arms all F engines, records anticipated sync time in config file. Returns the UTC time at which
        the system was sync'd in seconds since the Unix epoch (MCNT=0)
        If send_sync = True, a manual software sync will be sent to the F-Engines after arming.
        """
        #wait for within 100ms of a half-second, then send out the arm signal.
        #TODO This code is ripped from medicina. Is it even right?
        self._logger.info('Issuing F-Engine arm')
        ready=0
        while not ready:
            ready=((int(time.time()*10+5)%10)==0)
        self.sync_time=int(time.time())+1
        self.all_fengs('arm_trigger')
        if send_sync:
            # send two syncs, as the first is flushed
            self.all_fengs('man_sync')
            self.all_fengs('man_sync')
        self.redis_host.set('sync_time', self.sync_time)
        return self.sync_time

    def load_sync(self):
        """Determines if a sync_time exists, returns that value else return 0"""
        t = self.redis_host.get('sync_time')
        if t is None:
            self._logger.warning("No previous Sync Time found, defaulting to 0 seconds since the Unix Epoch")
            self.sync_time = 0
        else:
            self.sync_time = t
            self._logger.info('sync time is %d (%s)'%(self.sync_time, time.ctime(self.sync_time)))
        return self.sync_time


    def parse_config_file(self):
        """
        Parse the instance's config file, saving some parameters as attributes
        for easy access.
        This method is automatically called on object instantiation.
        """
        #some common params
        self.n_ants  = self.config['Configuration']['correlator']['hardcoded']['n_ants']
        self.n_bands = self.config['Configuration']['correlator']['hardcoded']['n_bands']
        self.n_inputs= self.config['Configuration']['correlator']['hardcoded']['inputs_per_board']
        self.n_chans = self.config['Configuration']['correlator']['hardcoded']['n_chans']
        self.n_pols  = self.config['Configuration']['correlator']['hardcoded']['n_pols']
        self.output_format  = self.config['Configuration']['correlator']['hardcoded']['output_format']
        self.acc_len  = self.config['Configuration']['correlator']['runtime']['acc_len']
        self.data_path  = self.config['Configuration']['correlator']['runtime']['data_path']
        self.adc_clk  = self.config['FEngine']['adc_clk']
        self.lo_freq  = self.config['FEngine']['mix_freq']
        self.n_bls = (self.n_ants * (self.n_ants + 1))/2
        self.bl_order = sim.get_bl_order(self.n_bls)

        self.roaches = set([node['host'] for node in self.config['FEngine']['nodes']+self.config['XEngine']['nodes']])

        #shortcuts to sections
        self.c_testing = self.config['Configuration']['correlator']['runtime']['testing']
        self.c_correlator = self.config['Configuration']['correlator']['runtime']
        self.c_correlator_hard = self.config['Configuration']['correlator']['hardcoded']
        self.c_global = self.config['Configuration']
        self.c_antennas = self.config['Antennas']
        self.c_array = self.config['Array']

        # some debugging / info
        self._logger.info("ROACHes are %r"%self.roaches)
        
        # ant array shortcuts
        self.array_lon = self.c_array['lon']
        self.array_lat = self.c_array['lat']
        self.ant_locs = [[0., 0., 0.] for a in self.c_antennas]
        for ant in self.c_antennas:
            self.ant_locs[ant['ant']] = ant['loc'] #this way the ants don't have to be in order in the config file

        self.array = antenna_functions.AntArray((self.array_lat, self.array_lon), self.ant_locs)


    def connect_to_roaches(self):
        """
        Set up katcp connections to all ROACHes in the correlator config file.
        Add the FpgaClient instances to the self.fpgas list.
        Returns a list of boolean values, corresponding to the connection
        state of each ROACH in the system.
        """
        self.fpgas = {}
        connected = {}
        for rn,roachhost in enumerate(self.roaches):
            self._logger.info("Connecting to ROACH %d, %s"%(rn,roachhost))
            self.fpgas[roachhost] = roach.Roach(roachhost,boffile=self.c_global['boffile'])
            time.sleep(0.01)
            connected[roachhost] = self.fpgas[roachhost].is_connected()
            if not connected[roachhost]:
                self._logger.error('Could not connect to roachhost: %s'%roachhost)
        return connected

    def initialise_f_engines(self,passive=False):
        """
        Instantiate an FEngine instance for each one specified in the correlator config file.
        Append the FEngine instances to the self.fengs list.
        """
        self.fengs = []
        for fn, feng in enumerate(self.config['FEngine']['nodes']):
            feng_attrs = {}
            for key in feng.keys():
                feng_attrs[key] = feng[key]
            for key in self.config['FEngine'].keys():
                if key not in feng_attrs.keys():
                    feng_attrs[key] = self.config['FEngine'][key]
            self._logger.info('Constructing F-engine %d (roach: %s, ant: %d, band: %s)'%(fn, feng['host'], feng['ant'], feng['band']))
            self.fengs.append(engines.FEngine(self.fpgas[feng['host']], 
                                      connect_passively=passive,
                                      num=fn, **feng_attrs))
        self.n_fengs = len(self.fengs)
        self._logger.info('%d F-engines constructed'%self.n_fengs)

    def initialise_x_engines(self,passive=False):
        """
        Instantiate an XEngine instance for each one specified in the correlator config file.
        Append the XEngine instances to the self.xengs list.
        """
        self.xengs = []
        for xn, xeng in enumerate(self.config['XEngine']['nodes']):
            self._logger.info('Constructing X-engine %d (roach: %s)'%(xn, xeng['host']))
            self.xengs.append(engines.XEngine(self.fpgas[xeng['host']],'ctrl',band=xeng['band'],n_ants=self.n_ants,chans=self.config['XEngine']['n_chans'], connect_passively=passive, acc_len=self.acc_len, num=xn))
        self.n_xengs = len(self.xengs)
        self._logger.info('%d X-engines constructed'%self.n_xengs)

    def all_fengs(self, method, *args, **kwargs):
        """
        Call FEngine method 'method' against all FEngine instances.
        Optional arguments are passed to the FEngine method calls.
        If an attribute rather than a method is specified, the attribute value
        will be returned as a list (one entry for each F-Engine). Otherwise the
        return value is that of the underlying FEngine method call.
        """
        self._logger.debug('Calling method %s against all F-engines in single-thread mode'%method)
        if callable(getattr(engines.FEngine,method)):
            return [getattr(feng, method)(*args, **kwargs) for feng in self.fengs]
        else:
            # no point in multithreading this
            return [getattr(feng,method) for feng in self.fengs]

    def all_fengs_multithread(self, method, *args, **kwargs):
        """
        Call FEngine method 'method' against all FEngine instances.
        Use a different thread per engine so calls don't block. This
        is useful for things like snapshot_get() where we might not
        want to wait for a snapshot to be grabbed before moving on to
        the next engine.
        Optional arguments are passed to the FEngine method calls.
        If an attribute rather than a method is specified, the attribute value
        will be returned as a list (one entry for each F-Engine). Otherwise the
        return value is that of the underlying FEngine method call.
        """
        self._logger.debug('Calling method %s against all F-engines in multi-thread mode'%method)
        if callable(getattr(engines.FEngine,method)):
            q = Queue.Queue()
            for feng in self.fengs:
                t = threading.Thread(target=_queue_instance_method, args=(q, feng.num, feng, method, args, kwargs))
                t.daemon = True
                t.start()
            self._logger.debug('Threads joining')
            q.join()
            self._logger.debug('Threads joined')
            rv = [None for feng in self.fengs]
            for fn, feng in enumerate(self.fengs):
                num, result = q.get()
                rv[num] = result
            return rv
        else:
            # no point in multithreading this
            return [getattr(feng,method) for feng in self.fengs]

    def all_xengs(self, method, *args, **kwargs):
        """
        Call XEngine method 'method' against all XEngine instances.
        Optional arguments are passed to the XEngine method calls.
        If an attribute rather than a method is specified, the attribute value
        will be returned as a list (one entry for each X-Engine). Otherwise the
        return value is that of the underlying XEngine method call.
        """
        self._logger.debug('Calling method %s against all X-engines in single-thread mode'%method)
        if callable(getattr(engines.XEngine,method)):
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
        self._logger.debug('Calling method %s against all ROACHes in single-thread mode'%method)
        if callable(getattr(roach.Roach,method)):
            return [getattr(fpga, method)(*args, **kwargs) for fpgas in self.fpgas.values()]
        else:
            return [getattr(fpga,method) for fpga in self.fpgas.values()]

    def program_all(self,reinitialise=True):
        """
        Program all ROACHs. Since F and X engines share boards, programming via this method
        is preferable to programming via the F/XEngine instances.
        By default, F/X instances are rebuild after reprogramming, and FEngine ADCs are recalibrated.
        If reinitialise=False, no engines are instantiated (you will have to call initialise_f/x_engines
        manually.)
        """
        for roach in self.fpgas.values():
            self._logger.info("Programming ROACH %s with boffile %s"%(roach.host,roach.boffile))
            roach.safe_prog()
        if reinitialise:
            # reprogramming messes with ctrl_sw, etc, so clean out the engine lists
            self._logger.info("Re-initializing engines")
            self.initialise_f_engines(passive=False)
            self.initialise_x_engines(passive=False)
        else:
            self._logger.warning("Not re-initializing engines. Danger of sw/fw desync")
            self.fengs = []
            self.xengs = []
        for fn,feng in enumerate(self.fengs):
            feng.calibrate_adc()
    def get_array_config(self):
        pass
        


class AmiSbl(AmiDC):
    """
    A subclass of AmiDC for the single-ROACH, single-baseline correlator
    """
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
                temp   = np.array(struct.unpack(c_pack_format,xeng.read('corr01_bram',2*n_bytes)))
                temp_flipped = np.zeros_like(temp)
                temp_flipped[0::2] = temp[-2::-2]
                temp_flipped[1::2] = temp[-1::-2]
                snap01[2*(self.n_bands-1)*self.n_chans:2*self.n_bands*self.n_chans]   = temp_flipped[:]
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

    def set_phase_switches(self, override=None):
        '''
        Override phase switches enable with specified state.
        If no state is given, set to the default enabled
        state from the config file.
        '''
        for fn, feng in enumerate(self.fengs):
            if override is not None:
                self._logger.warning('Overriding phase switch enable state of feng %d to %s'%(fn, override))
                feng.phase_switch_enable(override)
            else:
                self._logger.info('Setting phase switch enable state of feng %d to %s'%(fn, feng.phase_switch))
                feng.phase_switch_enable(feng.phase_switch)

    def mcnt2time(self,mcnt):
        """
        Convert an mcnt to a UTC time based on the instance's sync_time attribute.
        """
        conv_factor = 16./(self.adc_clk*1e6)
        offset = self.sync_time
        return offset + mcnt*conv_factor
