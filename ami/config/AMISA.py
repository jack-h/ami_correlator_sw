import numpy as np
import aipy as a

lat = 52.1674*np.pi/180.
lon = 0.03264*np.pi/180.

sl = np.sin(lat)
cl = np.cos(lat)

ant6 = np.array([11.2184,22.0568,-0.0230]) #position N,E,h in m
ant7 = np.array([12.2961,5.7293,0.0366])

M = np.array([[-sl,0,0],[0,1,0],[cl,0,0]])

ant6_eq = np.dot(M,ant6) #equatorial positions, z = NCP, y = East, x = radial in plane of equator
ant7_eq = np.dot(M,ant7)

prms ={
    'loc'   : ('52:10:2.64','0:01:57.5'), # Lord's Bridge
    'antpos': np.array([ant6_eq,ant7_eq])/3e8 * 1e9, #co-ords in light ns
    'amps'  : [1.,1.],
    'dec'   : 52.1706*np.pi/180.,
    'bp_r': np.array([[1.]] * 2),
    'bp_i': np.array([[1.]] * 2),
    'beam': a.fit.Beam2DGaussian,
    'bm_prms': {'xwidth':0.1151, 'ywidth':0.0994}, #nonsense copied from medicina
}

class AntennaArray(a.fit.AntennaArray):
    """Include functions to necessary for the pointing of the Medicina BEST-2 array"""
    def dec_pointing(self, dec):
        self.dec_pointing = dec
    def get_baseline(self, i, j, src='z'):
        """Return the baseline corresponding to i,j in various coordinate 
        projections: src='e' for current equatorial, 'z' for zenith 
        topocentric, 'r' for unrotated equatorial, or a RadioBody for
        projection toward that source."""
        bl = self[j] - self[i]
        #print bl
        if type(src) == str:
            if src == 'e': return np.dot(self._eq2now, bl)
            elif src == 'z': return np.dot(self._eq2zen, bl)
            elif src == 'r': return bl
            else: raise ValueError('Unrecognized source:' + src)
        try:
            if src.alt < 0:
                raise a.phs.PointingError('%s below horizon' % src.src_name)
            m = src.map
            #if i==0 and j==1: print self.sidereal_time(),self.sidereal_time() - src.ra, self.dec_pointing - src.dec
            #m = a.coord.eq2top_m(self.sidereal_time() - src.ra, self.dec_pointing - src.dec)
            #m = a.coord.eq2top_m(self.sidereal_time() - src.ra, 0.)
        except(AttributeError):
            ra,dec = a.coord.eq2radec(src)
            m = a.coord.eq2top_m(self.sidereal_time() - ra, dec)
        #print np.dot(m, bl).transpose()
        return np.dot(m, bl).transpose()

def get_aa(freqs):
    '''Return the AntennaArray to be used fro simulationp.'''
    location = prms['loc']
    antennas = []
    nants = len(prms['antpos'])
    for i in range(len(prms['antpos'])):
        beam = prms['beam'](freqs)
        try: beam.set_params(prms['bm_prms'])
        except(AttributeError): pass
        pos = prms['antpos'][i]
        bp_r = prms['bp_r'][i]
        bp_i = prms['bp_i'][i]
        antennas.append(
            a.fit.Antenna(pos[0],pos[1],pos[2], beam,
                bp_r=bp_r, bp_i=bp_i)
        )
    aa = AntennaArray(prms['loc'], antennas)
    aa.dec_pointing(prms['dec'])
    return aa

src_prms = {
}
