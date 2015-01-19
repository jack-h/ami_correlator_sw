import struct, logging, time
import corr.katcp_wrapper as katcp
import helpers
import numpy as np

logger = helpers.add_default_log_handlers(logging.getLogger(__name__))

class Roach(katcp.FpgaClient):
    '''
    A minor expansion on the FpgaClient class adds a few methods.
    '''
    def __init__(self, roachhost, port=7147, boffile=None, logger=logger):
        katcp.FpgaClient.__init__(self,roachhost, port, logger=logger)
        self.boffile = boffile
        # self._logger should be set by the FpgaClient class,
        # but looking at the katcp code I'm not convinced
        # that it is properly passed up the chain of classes
        # TODO: is there a typo in the katcp CallbackClient class __init__?
        # Should the superclass be constructed with logger=log, not logger=logger?
        self._logger = logger

    def snap(self,name,format='L',**kwargs):
        """
        A wrapper for snapshot_get(name, **kwargs), which decodes data into a numpy array, based on the format argument.
        Big endianness is assumped, so only pass the format character. (i.e., 'L' for unsigned 32 bit, etc).
        See the python struct manual for details of available formats.
        """

        self._logger.debug('Snapping register %s (assuming format %s)'%(name, format))
        n_bytes = struct.calcsize('=%s'%format)
        d = self.snapshot_get(name, **kwargs)
        self._logger.debug('Got %d bytes'%d['length'])
        return np.array(struct.unpack('>%d%s'%(d['length']/n_bytes,format),d['data']))

    def calibrate_qdr(self, qdrname, verbosity=1):
        qdr = qdr.Qdr(fpga, name)
        qdr.qdr_cal(fail_hard=True, verbosity=verbosity)

    def safe_prog(self, check_clock=True):
        """
        A wrapper for the FpgaClient progdev method.
        This method checks the target boffile is available before attempting to program, and clears
        the FPGA before programming. A test write to the sys_scratchpad register is performed after programming.
        If check_clock=True, the FPGA clock rate is estimated via katcp and returned in MHz.
        """
        if self.boffile not in self.listbof():
            self._logger.critical("boffile %s not available on ROACH %s"%(self.boffile,self.host))
            raise RuntimeError("boffile %s not available on ROACH %s"%(self.boffile,self.host))
        self.progdev('')
        time.sleep(0.1)
        self.progdev(self.boffile)
        time.sleep(0.1)
        # write_int automatically does a read check. The following call will fail
        # if the roach hasn't programmed properly
        self.write_int('sys_scratchpad',0xdeadbeef)
        if check_clock:
            clk = self.est_brd_clk()
            self._logger.info('Board clock is approx %.3f MHz'%clk)
            return clk
        else:
            return None

    def set_boffile(self,boffile):
        """
        Set the self.boffile attribute, which is used in safe_prog calls.
        """
        self.boffile=boffile
