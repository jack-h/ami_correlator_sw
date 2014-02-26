import numpy as np

def uint2int(d,bits,bp,complex=False):
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
    return 10*np.log10(x)

def slice(val,lsb,width=1):
    out = (val & ((2**width - 1) << lsb)) >> lsb
    if width == 1:
        return bool(out)
    else:
        return out
