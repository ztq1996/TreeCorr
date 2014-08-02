/* Copyright (c) 2003-2014 by Mike Jarvis
 *
 * TreeCorr is free software: redistribution and use in source and binary forms,
 * with or without modification, are permitted provided that the following
 * conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice, this
 *    list of conditions, and the disclaimer given in the accompanying LICENSE
 *    file.
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 *    this list of conditions, and the disclaimer given in the documentation
 *    and/or other materials provided with the distribution.
 * 3. Neither the name of the {organization} nor the names of its
 *    contributors may be used to endorse or promote products derived from
 *    this software without specific prior written permission.
 */

#include "Field.h"
#include "Cell.h"
#include "dbg.h"

// To turn on debugging statements, set dbgout to &std::cerr or some other stream.
std::ostream* dbgout=&std::cerr;
// For even more debugging, set this to true.
bool XDEBUG = true;

// Most of the functionality for building Cells and doing the correlation functions is the
// same regardless of which kind of Cell we have (N, K, G) or which kind of positions we
// are using (Flat, Sphere).  So most of the C++ code uses templates.  
// DC = GData for shear 
//      KData for kappa
//      NData for counts
// M = Flat for flat-sky coordinates
//     Sphere for spherical coordinates

// This function just works on the top level data to figure out which data goes into
// each top-level Cell.  It is building up the top_* vectors, which can then be used
// to build the actual Cells.
template <int DC, int M>
void SetupTopLevelCells(
    std::vector<CellData<DC,M>*>& celldata,
    double minsizesq, double maxsizesq,
    SplitMethod sm, size_t start, size_t end,
    std::vector<CellData<DC,M>*>& top_data,
    std::vector<double>& top_sizesq,
    std::vector<size_t>& top_start, std::vector<size_t>& top_end)
{
    xdbg<<"Start SetupTopLevelCells: start,end = "<<start<<','<<end<<std::endl;
    xdbg<<"minsizesq = "<<minsizesq<<", maxsizesq = "<<maxsizesq<<std::endl;
    // The structure of this is very similar to the Cell constructor.
    // The difference is that here we only construct a new Cell (and do the corresponding
    // calculation of the averages) if the size is small enough.  At that point, the 
    // rest of the construction is passed onto the Cell class.
    CellData<DC,M>* ave;
    double sizesq;
    if (end-start == 1) {
        xdbg<<"Only 1 CellData entry: size = 0\n";
        ave = celldata[start];
        celldata[start] = 0; // Make sure the calling function doesn't delete this!
        sizesq = 0.;
    } else {
        ave = new CellData<DC,M>(celldata,start,end);
        sizesq = CalculateSizeSq(ave->getPos(),celldata,start,end);
        xdbg<<"size = "<<sqrt(sizesq)<<std::endl;
    }

    if (sizesq <= maxsizesq) {
        xdbg<<"Small enough.  Make a cell.\n";
        if (end-start > 1) ave->finishAverages(celldata,start,end);
        top_data.push_back(ave);
        top_sizesq.push_back(sizesq);
        top_start.push_back(start);
        top_end.push_back(end);
    } else {
        size_t mid = SplitData(celldata,sm,start,end,ave->getPos());
        xdbg<<"Too big.  Recurse with mid = "<<mid<<std::endl;
        SetupTopLevelCells(celldata, minsizesq, maxsizesq, sm, start, mid,
                           top_data, top_sizesq, top_start, top_end);
        SetupTopLevelCells(celldata, minsizesq, maxsizesq, sm, mid, end,
                           top_data, top_sizesq, top_start, top_end);
    }
}

// Specialize for all the different kinds of CellData possibilities.
template <int DC, int M>
CellData<DC,M>* BuildCellData(double x, double y, double g1, double g2, double k, double w);

template <>
CellData<GData,Flat>* BuildCellData(double x, double y, double g1, double g2, double, double w)
{ return new CellData<GData,Flat>(Position<Flat>(x,y), std::complex<double>(g1,g2), w); }

template <>
CellData<GData,Sphere>* BuildCellData(double ra, double dec, double g1, double g2, double, double w)
{ return new CellData<GData,Sphere>(Position<Sphere>(ra,dec), std::complex<double>(g1,g2), w); }

template <>
CellData<KData,Flat>* BuildCellData(double x, double y, double , double , double k, double w)
{ return new CellData<KData,Flat>(Position<Flat>(x,y), k, w); }

template <>
CellData<KData,Sphere>* BuildCellData(double ra, double dec, double , double , double k, double w)
{ return new CellData<KData,Sphere>(Position<Sphere>(ra,dec), k, w); }

template <>
CellData<NData,Flat>* BuildCellData(double x, double y, double , double , double, double w)
{ return new CellData<NData,Flat>(Position<Flat>(x,y), w); }

template <>
CellData<NData,Sphere>* BuildCellData(double ra, double dec, double , double , double, double w)
{ return new CellData<NData,Sphere>(Position<Sphere>(ra,dec), w); }


template <int DC, int M>
Field<DC,M>::Field(
    double* x, double* y, double* g1, double* g2, double* k, double* w,
    long nobj, double minsep, double maxsep, double b, int sm_int)
{
    dbg<<"Starting to Build Field with "<<nobj<<" objects\n";
    std::vector<CellData<DC,M>*> celldata;
    celldata.reserve(nobj);
    for(int i=0;i<nobj;++i) {
        if (w[i] != 0.)
            celldata.push_back(BuildCellData<DC,M>(x[i],y[i],g1[i],g2[i],k[i],w[i]));
    }
    xdbg<<"Built celldata with "<<celldata.size()<<" entries\n";

    // We don't build Cells that are too big or too small based on the min/max separation:

    // The minimum size cell that will be useful is one where two cells that just barely
    // don't split have (d + s1 + s2) = minsep
    // The largest s2 we need to worry about is s2 = 2s1.
    // i.e. d = minsep - 3s1  and s1 = 0.5 * bd
    //      d = minsep - 1.5 bd
    //      d = minsep / (1+1.5 b)
    //      s = 0.5 * b * minsep / (1+1.5 b)
    //        = b * minsep / (2+3b)
    double minsize = minsep * b / (2.+3.*b);
    double minsizesq = minsize * minsize;
    xdbg<<"minsizesq = "<<minsizesq<<std::endl;

    // The maximum size cell that will be useful is one where a cell of size s will
    // be split at the maximum separation even if the other size = 0.
    // i.e. s = b * maxsep
    double maxsize = maxsep * b;
    double maxsizesq = maxsize * maxsize;
    xdbg<<"maxsizesq = "<<maxsizesq<<std::endl;

    // Convert from the int to our enum.
    SplitMethod sm = static_cast<SplitMethod>(sm_int);

    // This is done in two parts so that we can do the (time-consuming) second part in 
    // parallel.
    // First we setup what all the top-level cells are going to be.
    // Then we build them and their sub-nodes.

    if (maxsizesq == 0.) {
        dbg<<"Doing brute-force calculation (all cells are leaf nodes).\n";
        // If doing a brute-force calculation, the top-level cell data are the same as celldata.
        const size_t n = celldata.size();
        _cells.resize(n);
#ifdef _OPENMP
#pragma omp parallel for
#endif
        for(int i=0;i<n;++i) {
            _cells[i] = new Cell<DC,M>(celldata[i]);
            celldata[i] = 0; // Make sure the calling routing doesn't delete this one.
        }
    } else {
        std::vector<CellData<DC,M>*> top_data;
        std::vector<double> top_sizesq;
        std::vector<size_t> top_start;
        std::vector<size_t> top_end;

        // Setup the top level cells:
        SetupTopLevelCells(celldata,minsizesq,maxsizesq,sm,0,celldata.size(),
                           top_data,top_sizesq,top_start,top_end);
        const size_t n = top_data.size();
        dbg<<"Field has "<<n<<" top-level nodes.  Building lower nodes...\n";
        _cells.resize(n);
#ifdef _OPENMP
#pragma omp parallel for
#endif
        for(int i=0;i<n;++i)
            _cells[i] = new Cell<DC,M>(top_data[i],top_sizesq[i],celldata,minsizesq,sm,
                                       top_start[i],top_end[i]);
    }

    // delete any CellData elements that didn't get kept in the _cells object.
    for (size_t i=0;i<celldata.size();++i) if (celldata[i]) delete celldata[i];
}

template <int DC, int M>
Field<DC,M>::~Field()
{
    for(size_t i=0; i<_cells.size(); ++i) delete _cells[i];
}

//
//
// Now the C-C++ interface functions that get used in python:
//
//

void* BuildGFieldFlat(double* x, double* y, double* g1, double* g2, double* w,
                      long nobj, double minsep, double maxsep, double b, int sm_int)
{
    dbg<<"Start BuildGFieldFlat\n";
    // Use w for k in this call to make sure k[i] is valid and won't seg fault.
    // The actual value of k[i] is ignored.
    void* field = static_cast<void*>(new Field<GData,Flat>(x, y, g1, g2, w, w, nobj,
                                                           minsep, maxsep, b, sm_int));
    dbg<<"field = "<<field<<std::endl;
    return field;
}

void* BuildGFieldSphere(double* ra, double* dec, double* g1, double* g2, double* w,
                        long nobj, double minsep, double maxsep, double b, int sm_int)
{
    dbg<<"Start BuildGFieldSphere\n";
    void* field = static_cast<void*>(new Field<GData,Sphere>(ra, dec, g1, g2, w, w, nobj,
                                                             minsep, maxsep, b, sm_int));
    dbg<<"field = "<<field<<std::endl;
    return field;
}

void* BuildKFieldFlat(double* x, double* y, double* k, double* w,
                      long nobj, double minsep, double maxsep, double b, int sm_int)
{
    dbg<<"Start BuildKFieldFlat\n";
    void* field = static_cast<void*>(new Field<KData,Flat>(x, y, w, w, k, w, nobj,
                                                           minsep, maxsep, b, sm_int));
    dbg<<"field = "<<field<<std::endl;
    return field;
}

void* BuildKFieldSphere(double* ra, double* dec, double* k, double* w,
                        long nobj, double minsep, double maxsep, double b, int sm_int)
{
    dbg<<"Start BuildKFieldSphere\n";
    void* field = static_cast<void*>(new Field<KData,Sphere>(ra, dec, w, w, k, w, nobj,
                                                             minsep, maxsep, b, sm_int));
    dbg<<"field = "<<field<<std::endl;
    return field;
}

void* BuildNFieldFlat(double* x, double* y, double* w,
                      long nobj, double minsep, double maxsep, double b, int sm_int)
{
    dbg<<"Start BuildNFieldFlat\n";
    void* field = static_cast<void*>(new Field<NData,Flat>(x, y, w, w, w, w, nobj,
                                                           minsep, maxsep, b, sm_int));
    dbg<<"field = "<<field<<std::endl;
    return field;
}

void* BuildNFieldSphere(double* ra, double* dec, double* w,
                        long nobj, double minsep, double maxsep, double b, int sm_int)
{
    dbg<<"Start BuildNFieldSphere\n";
    void* field = static_cast<void*>(new Field<NData,Sphere>(ra, dec, w, w, w, w, nobj,
                                                             minsep, maxsep, b, sm_int));
    dbg<<"field = "<<field<<std::endl;
    return field;
}

void DestroyGFieldFlat(void* field)
{
    dbg<<"Start DestroyGFieldFlat\n";
    dbg<<"field = "<<field<<std::endl;
    delete static_cast<Field<GData,Flat>*>(field);
}

void DestroyGFieldSphere(void* field)
{
    dbg<<"Start DestroyGFieldSphere\n";
    dbg<<"field = "<<field<<std::endl;
    delete static_cast<Field<GData,Sphere>*>(field);
}

void DestroyKFieldFlat(void* field)
{ 
    dbg<<"Start DestroyKFieldFlat\n";
    dbg<<"field = "<<field<<std::endl;
    delete static_cast<Field<KData,Flat>*>(field);
}

void DestroyKFieldSphere(void* field)
{
    dbg<<"Start DestroyKFieldSphere\n";
    dbg<<"field = "<<field<<std::endl;
    delete static_cast<Field<KData,Sphere>*>(field);
}

void DestroyNFieldFlat(void* field)
{ 
    dbg<<"Start DestroyNFieldFlat\n";
    dbg<<"field = "<<field<<std::endl;
    delete static_cast<Field<KData,Flat>*>(field);
}

void DestroyNFieldSphere(void* field)
{
    dbg<<"Start DestroyNFieldSphere\n";
    dbg<<"field = "<<field<<std::endl;
    delete static_cast<Field<NData,Sphere>*>(field);
}

