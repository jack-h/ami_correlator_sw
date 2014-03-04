import numpy as np

def uint2int(d,bits,bp,complex=False):
    """
    Convert unsigned integers to signed values and return them
    d: array of unsigned data
    bits: number of bits in output
    bp: binary point of output data
    complex: True if input data follows casper standard complex format.
    False if data should be interpreted as real
    """
    if complex:
        dout_r = (np.array(d) & (((2**bits)-1)<<bits)) >> bits
        dout_i = np.array(d) & ((2**bits)-1)
        dout_r = uint2int(dout_r,bits,bp,complex=False)
        dout_i = uint2int(dout_i,bits,bp,complex=False)
        return dout_r + 1j*dout_i
    else:
        dout = np.array(d,dtype=float)
        dout[dout>(2**(bits-1))] -= 2**bits
        dout /= 2**bp
        return dout

def dbs(x):
    """
    return 10*log10(x)
    """
    return 10*np.log10(x)

def slice(val,lsb,width=1):
    """
    Return bits lsb+width-1 downto lsb of val
    If the output width is 1 bit, convert result to bool.
    """
    out = (val & ((2**width - 1) << lsb)) >> lsb
    if width == 1:
        return bool(out)
    else:
        return out
