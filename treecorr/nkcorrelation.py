# Copyright (c) 2003-2014 by Mike Jarvis
#
# TreeCorr is free software: redistribution and use in source and binary forms,
# with or without modification, are permitted provided that the following
# conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions, and the disclaimer given in the accompanying LICENSE
#    file.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions, and the disclaimer given in the documentation
#    and/or other materials provided with the distribution.
# 3. Neither the name of the {organization} nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.


import treecorr
import numpy

# Start by loading up the relevant C functions using ctypes
import ctypes
import os

# The numpy version of this function tries to be more portable than the native
# ctypes.cdll.LoadLibary or cdtypes.CDLL functions.
_treecorr = numpy.ctypeslib.load_library('_treecorr',os.path.dirname(__file__))


class NKCorrelation(treecorr.BinnedCorr2):
    """This class handles the calculation and storage of a 2-point shear-shear correlation
    function.

    It holds the following attributes:

        logr        The nominal center of the bin in log(r).
        meanlogr    The (weighted) mean value of log(r) for the pairs in each bin.
                    If there are no pairs in a bin, then logr will be used instead.
        xi          The correlation function, xi(r).
        varxi       The variance of xi, only including the shot noise propagated into the
                    final correlation.  This does not include sample variance, so it is
                    always an underestimate of the actual variance.
        weight      The total weight in each bin.
        npairs      The number of pairs going into each bin.

    The usage pattern is as follows:

        nk = treecorr.NKCorrelation(config)
        nk.process(cat1,cat2)   # Compute the cross-correlation function.
        nk.write(file_name)     # Write out to a file.
        xi = nk.xi              # Or access the correlation function directly.
    """
    def __init__(self, config=None, logger=None, **kwargs):
        treecorr.BinnedCorr2.__init__(self, config, logger, **kwargs)

        self.xi = numpy.zeros(self.nbins, dtype=float)

        # an alias
        double_ptr = ctypes.POINTER(ctypes.c_double)

        xi = self.xi.ctypes.data_as(double_ptr)
        meanlogr = self.meanlogr.ctypes.data_as(double_ptr)
        weight = self.weight.ctypes.data_as(double_ptr)
        npairs = self.npairs.ctypes.data_as(double_ptr)

        _treecorr.BuildNKCorr.restype = ctypes.c_void_p
        _treecorr.BuildNKCorr.argtypes = [
            ctypes.c_double, ctypes.c_double, ctypes.c_int, ctypes.c_double, ctypes.c_double,
            double_ptr, double_ptr, double_ptr, double_ptr ]

        self.corr = _treecorr.BuildNKCorr(self.min_sep,self.max_sep,self.nbins,self.bin_size,self.b,
                                          xi,meanlogr,weight,npairs);
        self.logger.debug('Finished building NKCorr')

    def __del__(self):
        # Using memory allocated from the C layer means we have to explicitly deallocate it
        # rather than being able to rely on the Python memory manager.
        if hasattr(self,'data'):    # In case __init__ failed to get that far
            _treecorr.DestroyNKCorr.argtypes = [ ctypes.c_void_p ]
            _treecorr.DestroyNKCorr(self.corr)


    def process_cross(self, cat1, cat2):
        """Process a single pair of catalogs, accumulating the cross-correlation.

        This accumulates the weighted sums into the bins, but does not finalize
        the calculation by dividing by the total weight at the end.  After
        calling this function as often as desired, the finalize() command will
        finish the calculation.
        """
        self.logger.info('Starting process NK cross-correlations for cats %s, %s.',
                         cat1.file_name, cat2.file_name)
        nfield1 = cat1.getNField(self.min_sep,self.max_sep,self.b)
        kfield2 = cat2.getKField(self.min_sep,self.max_sep,self.b)

        if nfield1.sphere != kfield2.sphere:
            raise AttributeError("Cannot correlate catalogs with different coordinate systems.")

        if nfield1.sphere:
            _treecorr.ProcessCrossNKSphere.argtypes = [ 
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_voidp, ctypes.c_int ]
            _treecorr.ProcessCrossNKSphere(self.corr, nfield1.data, kfield2.data, self.output_dots)
        else:
            _treecorr.ProcessCrossNKFlat.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_voidp, ctypes.c_int ]
            _treecorr.ProcessCrossNKFlat(self.corr, nfield1.data, kfield2.data, self.output_dots)


    def finalize(self, vark):
        """Finalize the calculation of the correlation function.

        The process_cross command accumulates values in each bin, so it can be called
        multiple times if appropriate.  Afterwards, this command finishes the calculation
        by dividing each column by the total weight.
        """
        mask1 = self.npairs != 0
        mask2 = self.npairs == 0

        self.xi[mask1] /= self.weight[mask1]
        self.meanlogr[mask1] /= self.weight[mask1]
        self.varxi[mask1] = vark / self.npairs[mask1]

        # Update the units of meanlogr
        self.meanlogr[mask1] -= self.log_sep_units

        # Use meanlogr when available, but set to nominal when no pairs in bin.
        self.meanlogr[mask2] = self.logr[mask2]
        self.varxi[mask2] = 0.

    def clear(self):
        """Clear the data vectors
        """
        self.xi[:] = 0
        self.meanlogr[:] = 0
        self.weight[:] = 0
        self.npairs[:] = 0

    def process(self, cat1, cat2):
        """Compute the correlation function.

        Both arguments may be lists, in which case all items in the list are used 
        for that element of the correlation.
        """
        self.clear()

        if not isinstance(cat1,list): cat1 = [cat1]
        if not isinstance(cat2,list): cat2 = [cat2]
        if len(cat1) == 0:
            raise ValueError("No catalogs provided for cat1")
        if len(cat2) == 0:
            raise ValueError("No catalogs provided for cat2")

        vark = treecorr.calculateVarK(cat2)
        for c1 in cat1:
            for c2 in cat2:
                self.process_cross(c1,c2)
        self.finalize(vark)

    def calculateXi(self, rk=None):
        """Calculate the correlation function possibly given another correlation function
        that uses random points for the foreground objects.

        If rk is None, the simple correlation function <kappa> is returned.
        If rk is not None, then a compensated calculation is done: <kappa> = (nk - rk)
        """
        if rk is None:
            return self.xi
        else:
            return self.xi - rk.xi


    def write(self, file_name, rk=None):
        """Write the correlation function to the file, file_name.

        If rk is None, the simple correlation function <kappa>(R) is used.
        If rk is not None, then a compensated calculation is done: <kappa>(R) = (nk - rk)
        """
        self.logger.info('Writing NK correlations to %s',file_name)

        output = numpy.empty( (self.nbins, 6) )
        output[:,0] = numpy.exp(self.logr)
        output[:,1] = numpy.exp(self.meanlogr)
        output[:,2] = self.calculateXi(rk)
        output[:,3] = numpy.sqrt(self.varxi)
        output[:,4] = self.weight
        output[:,5] = self.npairs

        prec = self.config.get('precision',3)
        width = prec+8
        header_form = 5*("{:^%d}."%width) + "{:^%d}"%width
        header = header_form.format('R_nom','<R>','xi', 'sigma_xi','weight','npairs')
        fmt = '%%%d.%de'%(width,prec)
        numpy.savetxt(file_name, output, fmt=fmt, header=header)

    def writeM2(self, file_name):
        self.logger.info('Writing Map^2 from NK correlations to %s',file_name)
