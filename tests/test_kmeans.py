# Copyright (c) 2003-2019 by Mike Jarvis
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

from __future__ import print_function
import numpy as np
import os
import time
import coord
import warnings
import treecorr

from test_helper import get_from_wiki, CaptureLog, assert_raises, do_pickle, profile


def test_dessv():
    try:
        import fitsio
    except ImportError:
        print('Skipping dessv test, since fitsio is not installed')
        return

    #treecorr.set_omp_threads(1);
    get_from_wiki('des_sv.fits')
    file_name = os.path.join('data','des_sv.fits')
    cat = treecorr.Catalog(file_name, ra_col='ra', dec_col='dec', ra_units='deg', dec_units='deg')

    # Use an odd number to make sure we force some of the shuffle bits in InitializeCenters
    # to happen.
    npatch = 43
    field = cat.getNField()
    t0 = time.time()
    patches = field.run_kmeans(npatch)
    t1 = time.time()
    print('patches = ',np.unique(patches))
    assert len(patches) == cat.ntot
    assert min(patches) == 0
    assert max(patches) == npatch-1

    # KMeans minimizes the total inertia.
    # Check this value and the rms size, which should also be quite small.
    xyz = np.array([cat.x, cat.y, cat.z]).T
    cen = np.array([xyz[patches==i].mean(axis=0) for i in range(npatch)])
    inertia = np.array([np.sum((xyz[patches==i] - cen[i])**2) for i in range(npatch)])
    sizes = np.array([np.mean((xyz[patches==i] - cen[i])**2) for i in range(npatch)])**0.5
    sizes *= 180. / np.pi * 60.  # convert to arcmin
    counts = np.array([np.sum(patches==i) for i in range(npatch)])

    print('With standard algorithm:')
    print('time = ',t1-t0)
    print('total inertia = ',np.sum(inertia))
    print('mean inertia = ',np.mean(inertia))
    print('rms inertia = ',np.std(inertia))
    print('mean size = ',np.mean(sizes))
    print('rms size = ',np.std(sizes))
    assert np.sum(inertia) < 200.  # This is specific to this particular field and npatch.
    assert np.std(inertia) < 0.3 * np.mean(inertia)  # rms is usually < 0.2 * mean
    assert np.std(sizes) < 0.1 * np.mean(sizes)  # sizes have even less spread usually.

    # Should all have similar number of points.  Nothing is required here though.
    print('mean counts = ',np.mean(counts))
    print('min counts = ',np.min(counts))
    print('max counts = ',np.max(counts))

    # Check the alternate algorithm.  rms inertia should be lower.
    t0 = time.time()
    patches = field.run_kmeans(npatch, alt=True)
    t1 = time.time()
    assert len(patches) == cat.ntot
    assert min(patches) == 0
    assert max(patches) == npatch-1

    cen = np.array([xyz[patches==i].mean(axis=0) for i in range(npatch)])
    inertia = np.array([np.sum((xyz[patches==i] - cen[i])**2) for i in range(npatch)])
    sizes = np.array([np.mean((xyz[patches==i] - cen[i])**2) for i in range(npatch)])**0.5
    sizes *= 180. / np.pi * 60.  # convert to arcmin
    counts = np.array([np.sum(patches==i) for i in range(npatch)])

    print('With alternate algorithm:')
    print('time = ',t1-t0)
    print('total inertia = ',np.sum(inertia))
    print('mean inertia = ',np.mean(inertia))
    print('rms inertia = ',np.std(inertia))
    print('mean size = ',np.mean(sizes))
    print('rms size = ',np.std(sizes))
    assert np.sum(inertia) < 200.  # Total shouldn't increase much. (And often decreases.)
    assert np.std(inertia) < 0.1 * np.mean(inertia)  # rms should be even smaller here.
    assert np.std(sizes) < 0.1 * np.mean(sizes)  # This is only a little bit smaller.

    # This doesn't keep the counts as equal as the standard algorithm.
    print('mean counts = ',np.mean(counts))
    print('min counts = ',np.min(counts))
    print('max counts = ',np.max(counts))

    # Finally, use a field with lots of top level cells to check the other branch in
    # InitializeCenters.
    field = cat.getNField(min_top=10)
    t0 = time.time()
    patches = field.run_kmeans(npatch)
    t1 = time.time()
    assert len(patches) == cat.ntot
    assert min(patches) == 0
    assert max(patches) == npatch-1

    cen = np.array([xyz[patches==i].mean(axis=0) for i in range(npatch)])
    inertia = np.array([np.sum((xyz[patches==i] - cen[i])**2) for i in range(npatch)])
    sizes = np.array([np.mean((xyz[patches==i] - cen[i])**2) for i in range(npatch)])**0.5
    sizes *= 180. / np.pi * 60.  # convert to arcmin
    counts = np.array([np.sum(patches==i) for i in range(npatch)])

    # This doesn't give as good an initialization, so these are a bit worse usually.
    print('With min_top=10:')
    print('time = ',t1-t0)
    print('total inertia = ',np.sum(inertia))
    print('mean inertia = ',np.mean(inertia))
    print('rms inertia = ',np.std(inertia))
    print('mean size = ',np.mean(sizes))
    print('rms size = ',np.std(sizes))
    assert np.sum(inertia) < 210.
    assert np.std(inertia) < 0.4 * np.mean(inertia)  # I've seen over 0.3 x mean here.
    assert np.std(sizes) < 0.15 * np.mean(sizes)
    print('mean counts = ',np.mean(counts))
    print('min counts = ',np.min(counts))
    print('max counts = ',np.max(counts))



def test_radec():
    # Very similar to the above, but with a random set of points, so it will run even
    # if the user doesn't have fitsio installed.
    # In addition, we add weights to make sure that works.

    ngal = 100000
    s = 10.
    rng = np.random.RandomState(8675309)
    x = rng.normal(0,s, (ngal,) )
    y = rng.normal(0,s, (ngal,) ) + 100  # Put everything at large y, so smallish angle on sky
    z = rng.normal(0,s, (ngal,) )
    w = rng.random_sample(ngal)
    ra, dec = coord.CelestialCoord.xyz_to_radec(x,y,z)
    print('minra = ',np.min(ra) * coord.radians / coord.degrees)
    print('maxra = ',np.max(ra) * coord.radians / coord.degrees)
    print('mindec = ',np.min(dec) * coord.radians / coord.degrees)
    print('maxdec = ',np.max(dec) * coord.radians / coord.degrees)
    cat = treecorr.Catalog(ra=ra, dec=dec, ra_units='rad', dec_units='rad', w=w)

    npatch = 111
    field = cat.getNField()
    t0 = time.time()
    p = field.run_kmeans(npatch)
    t1 = time.time()
    print('patches = ',np.unique(p))
    assert len(p) == cat.ntot
    assert min(p) == 0
    assert max(p) == npatch-1

    xyz = np.array([cat.x, cat.y, cat.z]).T
    cen = np.array([np.average(xyz[p==i], axis=0, weights=w[p==i]) for i in range(npatch)])
    inertia = np.array([np.sum(w[p==i][:,None] * (xyz[p==i] - cen[i])**2) for i in range(npatch)])
    counts = np.array([np.sum(w[p==i]) for i in range(npatch)])

    print('With standard algorithm:')
    print('time = ',t1-t0)
    print('inertia = ',inertia)
    print('counts = ',counts)
    print('total inertia = ',np.sum(inertia))
    print('mean inertia = ',np.mean(inertia))
    print('rms inertia = ',np.std(inertia))
    assert np.sum(inertia) < 200.  # This is specific to this particular field and npatch.
    assert np.std(inertia) < 0.3 * np.mean(inertia)  # rms is usually small  mean

    # With weights, these aren't actually all that similar.  The range is more than a
    # factor of 10.  I think because it varies whether high weight points happen to be near the
    # edges or middles of patches, so the total weight varies when you target having the
    # inertias be relatively similar.
    print('mean counts = ',np.mean(counts))
    print('min counts = ',np.min(counts))
    print('max counts = ',np.max(counts))

    # Check the alternate algorithm.  rms inertia should be lower.
    t0 = time.time()
    p = field.run_kmeans(npatch, alt=True)
    t1 = time.time()
    assert len(p) == cat.ntot
    assert min(p) == 0
    assert max(p) == npatch-1

    cen = np.array([xyz[p==i].mean(axis=0) for i in range(npatch)])
    inertia = np.array([np.sum(w[p==i][:,None] * (xyz[p==i] - cen[i])**2) for i in range(npatch)])
    counts = np.array([np.sum(w[p==i]) for i in range(npatch)])

    print('With alternate algorithm:')
    print('time = ',t1-t0)
    print('total inertia = ',np.sum(inertia))
    print('mean inertia = ',np.mean(inertia))
    print('rms inertia = ',np.std(inertia))
    assert np.sum(inertia) < 200.  # Total shouldn't increase much. (And often decreases.)
    assert np.std(inertia) < 0.1 * np.mean(inertia)  # rms should be even smaller here.
    print('mean counts = ',np.mean(counts))
    print('min counts = ',np.min(counts))
    print('max counts = ',np.max(counts))

    # Finally, use a field with lots of top level cells to check the other branch in
    # InitializeCenters.
    field = cat.getNField(min_top=10)
    t0 = time.time()
    p = field.run_kmeans(npatch)
    t1 = time.time()
    assert len(p) == cat.ntot
    assert min(p) == 0
    assert max(p) == npatch-1

    cen = np.array([xyz[p==i].mean(axis=0) for i in range(npatch)])
    inertia = np.array([np.sum(w[p==i][:,None] * (xyz[p==i] - cen[i])**2) for i in range(npatch)])
    counts = np.array([np.sum(w[p==i]) for i in range(npatch)])

    # This doesn't give as good an initialization, so these are a bit worse usually.
    print('With min_top=10:')
    print('time = ',t1-t0)
    print('total inertia = ',np.sum(inertia))
    print('mean inertia = ',np.mean(inertia))
    print('rms inertia = ',np.std(inertia))
    assert np.sum(inertia) < 210.
    assert np.std(inertia) < 0.4 * np.mean(inertia)  # I've seen over 0.3 x mean here.
    print('mean counts = ',np.mean(counts))
    print('min counts = ',np.min(counts))
    print('max counts = ',np.max(counts))


def test_3d():
    # Like the above, but using x,y,z positions.

    ngal = 100000
    s = 1.
    rng = np.random.RandomState(8675309)
    x = rng.normal(0,s, (ngal,) )
    y = rng.normal(0,s, (ngal,) )
    z = rng.normal(0,s, (ngal,) )
    w = rng.random_sample(ngal) + 1
    cat = treecorr.Catalog(x=x, y=y, z=z, w=w)

    npatch = 111
    field = cat.getNField()
    t0 = time.time()
    p = field.run_kmeans(npatch)
    t1 = time.time()
    print('patches = ',np.unique(p))
    assert len(p) == cat.ntot
    assert min(p) == 0
    assert max(p) == npatch-1

    xyz = np.array([x, y, z]).T
    cen = np.array([np.average(xyz[p==i], axis=0, weights=w[p==i]) for i in range(npatch)])
    inertia = np.array([np.sum(w[p==i][:,None] * (xyz[p==i] - cen[i])**2) for i in range(npatch)])
    counts = np.array([np.sum(w[p==i]) for i in range(npatch)])

    print('With standard algorithm:')
    print('time = ',t1-t0)
    print('inertia = ',inertia)
    print('counts = ',counts)
    print('total inertia = ',np.sum(inertia))
    print('mean inertia = ',np.mean(inertia))
    print('rms inertia = ',np.std(inertia))
    assert np.sum(inertia) < 33000.
    assert np.std(inertia) < 0.3 * np.mean(inertia)  # rms is usually small  mean
    print('mean counts = ',np.mean(counts))
    print('min counts = ',np.min(counts))
    print('max counts = ',np.max(counts))

    # Should be the same thing with ra, dec, ra
    ra, dec = coord.CelestialCoord.xyz_to_radec(x,y,z)
    r = (x**2 + y**2 + z**2)**0.5
    cat2 = treecorr.Catalog(ra=ra, dec=dec, ra_units='rad', dec_units='rad', r=r, w=w)
    field = cat.getNField()
    t0 = time.time()
    p2 = field.run_kmeans(npatch)
    t1 = time.time()
    cen = np.array([np.average(xyz[p2==i], axis=0, weights=w[p2==i]) for i in range(npatch)])
    inertia = np.array([np.sum(w[p2==i][:,None] * (xyz[p2==i] - cen[i])**2) for i in range(npatch)])
    counts = np.array([np.sum(w[p2==i]) for i in range(npatch)])
    print('time = ',t1-t0)
    print('total inertia = ',np.sum(inertia))
    print('mean inertia = ',np.mean(inertia))
    print('rms inertia = ',np.std(inertia))
    assert np.sum(inertia) < 33000.
    assert np.std(inertia) < 0.3 * np.mean(inertia)  # rms is usually small  mean
    print('mean counts = ',np.mean(counts))
    print('min counts = ',np.min(counts))
    print('max counts = ',np.max(counts))

    # Check the alternate algorithm.  rms inertia should be lower.
    t0 = time.time()
    p = field.run_kmeans(npatch, alt=True)
    t1 = time.time()
    assert len(p) == cat.ntot
    assert min(p) == 0
    assert max(p) == npatch-1

    cen = np.array([xyz[p==i].mean(axis=0) for i in range(npatch)])
    inertia = np.array([np.sum(w[p==i][:,None] * (xyz[p==i] - cen[i])**2) for i in range(npatch)])
    counts = np.array([np.sum(w[p==i]) for i in range(npatch)])

    print('With alternate algorithm:')
    print('time = ',t1-t0)
    print('total inertia = ',np.sum(inertia))
    print('mean inertia = ',np.mean(inertia))
    print('rms inertia = ',np.std(inertia))
    assert np.sum(inertia) < 33000.
    assert np.std(inertia) < 0.1 * np.mean(inertia)  # rms should be even smaller here.
    print('mean counts = ',np.mean(counts))
    print('min counts = ',np.min(counts))
    print('max counts = ',np.max(counts))

    # Finally, use a field with lots of top level cells to check the other branch in
    # InitializeCenters.
    field = cat.getNField(min_top=10)
    t0 = time.time()
    p = field.run_kmeans(npatch)
    t1 = time.time()
    assert len(p) == cat.ntot
    assert min(p) == 0
    assert max(p) == npatch-1

    cen = np.array([xyz[p==i].mean(axis=0) for i in range(npatch)])
    inertia = np.array([np.sum(w[p==i][:,None] * (xyz[p==i] - cen[i])**2) for i in range(npatch)])
    counts = np.array([np.sum(w[p==i]) for i in range(npatch)])

    # This doesn't give as good an initialization, so these are a bit worse usually.
    print('With min_top=10:')
    print('time = ',t1-t0)
    print('total inertia = ',np.sum(inertia))
    print('mean inertia = ',np.mean(inertia))
    print('rms inertia = ',np.std(inertia))
    assert np.sum(inertia) < 33000.
    assert np.std(inertia) < 0.4 * np.mean(inertia)  # I've seen over 0.3 x mean here.
    print('mean counts = ',np.mean(counts))
    print('min counts = ',np.min(counts))
    print('max counts = ',np.max(counts))


def test_2d():
    # Like the above, but using x,y positions.
    # An additional check here is that this works with other fields besides NField, even though
    # in practice NField will alsmost always be the kind of Field used.

    ngal = 100000
    s = 1.
    rng = np.random.RandomState(8675309)
    x = rng.normal(0,s, (ngal,) )
    y = rng.normal(0,s, (ngal,) )
    w = rng.random_sample(ngal) + 1
    g1 = rng.normal(0,s, (ngal,) )
    g2 = rng.normal(0,s, (ngal,) )
    k = rng.normal(0,s, (ngal,) )
    cat = treecorr.Catalog(x=x, y=y, w=w, g1=g1, g2=g2, k=k)

    npatch = 111
    field = cat.getGField()
    t0 = time.time()
    p = field.run_kmeans(npatch)
    t1 = time.time()
    print('patches = ',np.unique(p))
    assert len(p) == cat.ntot
    assert min(p) == 0
    assert max(p) == npatch-1

    xy = np.array([x, y]).T
    cen = np.array([np.average(xy[p==i], axis=0, weights=w[p==i]) for i in range(npatch)])
    inertia = np.array([np.sum(w[p==i][:,None] * (xy[p==i] - cen[i])**2) for i in range(npatch)])
    counts = np.array([np.sum(w[p==i]) for i in range(npatch)])

    print('With standard algorithm:')
    print('time = ',t1-t0)
    print('inertia = ',inertia)
    print('counts = ',counts)
    print('total inertia = ',np.sum(inertia))
    print('mean inertia = ',np.mean(inertia))
    print('rms inertia = ',np.std(inertia))
    assert np.sum(inertia) < 5300.
    assert np.std(inertia) < 0.3 * np.mean(inertia)  # rms is usually small  mean
    print('mean counts = ',np.mean(counts))
    print('min counts = ',np.min(counts))
    print('max counts = ',np.max(counts))

    # Check the alternate algorithm.  rms inertia should be lower.
    t0 = time.time()
    p = field.run_kmeans(npatch, alt=True)
    t1 = time.time()
    assert len(p) == cat.ntot
    assert min(p) == 0
    assert max(p) == npatch-1

    cen = np.array([xy[p==i].mean(axis=0) for i in range(npatch)])
    inertia = np.array([np.sum(w[p==i][:,None] * (xy[p==i] - cen[i])**2) for i in range(npatch)])
    counts = np.array([np.sum(w[p==i]) for i in range(npatch)])

    print('With alternate algorithm:')
    print('time = ',t1-t0)
    print('total inertia = ',np.sum(inertia))
    print('mean inertia = ',np.mean(inertia))
    print('rms inertia = ',np.std(inertia))
    assert np.sum(inertia) < 5300.
    assert np.std(inertia) < 0.1 * np.mean(inertia)  # rms should be even smaller here.
    print('mean counts = ',np.mean(counts))
    print('min counts = ',np.min(counts))
    print('max counts = ',np.max(counts))

    # Finally, use a field with lots of top level cells to check the other branch in
    # InitializeCenters.
    field = cat.getKField(min_top=10)
    t0 = time.time()
    p = field.run_kmeans(npatch)
    t1 = time.time()
    assert len(p) == cat.ntot
    assert min(p) == 0
    assert max(p) == npatch-1

    cen = np.array([xy[p==i].mean(axis=0) for i in range(npatch)])
    inertia = np.array([np.sum(w[p==i][:,None] * (xy[p==i] - cen[i])**2) for i in range(npatch)])
    counts = np.array([np.sum(w[p==i]) for i in range(npatch)])

    # This doesn't give as good an initialization, so these are a bit worse usually.
    print('With min_top=10:')
    print('time = ',t1-t0)
    print('total inertia = ',np.sum(inertia))
    print('mean inertia = ',np.mean(inertia))
    print('rms inertia = ',np.std(inertia))
    assert np.sum(inertia) < 5300.
    assert np.std(inertia) < 0.4 * np.mean(inertia)  # I've seen over 0.3 x mean here.
    print('mean counts = ',np.mean(counts))
    print('min counts = ',np.min(counts))
    print('max counts = ',np.max(counts))


def test_init_random():
    # Test the init=random option

    ngal = 100000
    s = 1.
    rng = np.random.RandomState(8675309)
    x = rng.normal(0,s, (ngal,) )
    y = rng.normal(0,s, (ngal,) )
    z = rng.normal(0,s, (ngal,) )
    cat = treecorr.Catalog(x=x, y=y, z=z)
    xyz = np.array([x, y, z]).T

    # Skip the refine_centers step.
    print('3d with init=random')
    npatch = 10
    field = cat.getNField()
    cen1 = field.kmeans_initialize_centers(npatch, 'random')
    #print('cen = ',cen1)
    assert cen1.shape == (npatch, 3)
    p1 = field.kmeans_assign_patches(cen1)
    print('patches = ',np.unique(p1))
    assert len(p1) == cat.ntot
    assert min(p1) == 0
    assert max(p1) == npatch-1

    inertia1 = np.array([np.sum((xyz[p1==i] - cen1[i])**2) for i in range(npatch)])
    counts1 = np.array([np.sum(p1==i) for i in range(npatch)])
    print('counts = ',counts1)
    print('rms counts = ',np.std(counts1))
    print('total inertia = ',np.sum(inertia1))

    # Now run the normal way
    # Use higher max_iter, since random isn't a great initialization.
    p2 = field.run_kmeans(npatch, init='random', max_iter=1000)
    cen2 = np.array([xyz[p2==i].mean(axis=0) for i in range(npatch)])
    inertia2 = np.array([np.sum((xyz[p2==i] - cen2[i])**2) for i in range(npatch)])
    counts2 = np.array([np.sum(p2==i) for i in range(npatch)])
    print('rms counts => ',np.std(counts2))
    print('total inertia => ',np.sum(inertia2))
    assert np.sum(inertia2) < np.sum(inertia1)

    # Use a field with lots of top level cells
    print('3d with init=random, min_top=10')
    field = cat.getNField(min_top=10)
    cen1 = field.kmeans_initialize_centers(npatch, 'random')
    #print('cen = ',cen1)
    assert cen1.shape == (npatch, 3)
    p1 = field.kmeans_assign_patches(cen1)
    print('patches = ',np.unique(p1))
    assert len(p1) == cat.ntot
    assert min(p1) == 0
    assert max(p1) == npatch-1

    inertia1 = np.array([np.sum((xyz[p1==i] - cen1[i])**2) for i in range(npatch)])
    counts1 = np.array([np.sum(p1==i) for i in range(npatch)])
    print('counts = ',counts1)
    print('rms counts = ',np.std(counts1))
    print('total inertia = ',np.sum(inertia1))

    # Now run the normal way
    p2 = field.run_kmeans(npatch, init='random', max_iter=1000)
    cen2 = np.array([xyz[p2==i].mean(axis=0) for i in range(npatch)])
    inertia2 = np.array([np.sum((xyz[p2==i] - cen2[i])**2) for i in range(npatch)])
    counts2 = np.array([np.sum(p2==i) for i in range(npatch)])
    print('rms counts => ',np.std(counts2))
    print('total inertia => ',np.sum(inertia2))
    assert np.sum(inertia2) < np.sum(inertia1)

    # Repeat in 2d
    print('2d with init=random')
    cat = treecorr.Catalog(x=x, y=y)
    xy = np.array([x, y]).T
    field = cat.getNField()
    cen1 = field.kmeans_initialize_centers(npatch, 'random')
    #print('cen = ',cen1)
    assert cen1.shape == (npatch, 2)
    p1 = field.kmeans_assign_patches(cen1)
    print('patches = ',np.unique(p1))
    assert len(p1) == cat.ntot
    assert min(p1) == 0
    assert max(p1) == npatch-1

    inertia1 = np.array([np.sum((xy[p1==i] - cen1[i])**2) for i in range(npatch)])
    counts1 = np.array([np.sum(p1==i) for i in range(npatch)])
    print('counts = ',counts1)
    print('rms counts = ',np.std(counts1))
    print('total inertia = ',np.sum(inertia1))

    # Now run the normal way
    p2 = field.run_kmeans(npatch, init='random', max_iter=1000)
    cen2 = np.array([xy[p2==i].mean(axis=0) for i in range(npatch)])
    inertia2 = np.array([np.sum((xy[p2==i] - cen2[i])**2) for i in range(npatch)])
    counts2 = np.array([np.sum(p2==i) for i in range(npatch)])
    print('rms counts => ',np.std(counts2))
    print('total inertia => ',np.sum(inertia2))
    assert np.sum(inertia2) < np.sum(inertia1)

    # Repeat in spherical
    print('spher with init=random')
    ra, dec = coord.CelestialCoord.xyz_to_radec(x,y,z)
    cat = treecorr.Catalog(ra=ra, dec=dec, ra_units='rad', dec_units='rad')
    xyz = np.array([cat.x, cat.y, cat.z]).T
    field = cat.getNField()
    cen1 = field.kmeans_initialize_centers(npatch, 'random')
    #print('cen = ',cen1)
    assert cen1.shape == (npatch, 3)
    p1 = field.kmeans_assign_patches(cen1)
    print('patches = ',np.unique(p1))
    assert len(p1) == cat.ntot
    assert min(p1) == 0
    assert max(p1) == npatch-1

    inertia1 = np.array([np.sum((xyz[p1==i] - cen1[i])**2) for i in range(npatch)])
    counts1 = np.array([np.sum(p1==i) for i in range(npatch)])
    print('counts = ',counts1)
    print('rms counts = ',np.std(counts1))
    print('total inertia = ',np.sum(inertia1))

    # Now run the normal way
    p2 = field.run_kmeans(npatch, init='random', max_iter=1000)
    cen2 = np.array([xyz[p2==i].mean(axis=0) for i in range(npatch)])
    inertia2 = np.array([np.sum((xyz[p2==i] - cen2[i])**2) for i in range(npatch)])
    counts2 = np.array([np.sum(p2==i) for i in range(npatch)])
    print('rms counts => ',np.std(counts2))
    print('total inertia => ',np.sum(inertia2))
    assert np.sum(inertia2) < np.sum(inertia1)

    with assert_raises(ValueError):
        field.run_kmeans(npatch, init='invalid')
    with assert_raises(ValueError):
        field.kmeans_initialize_centers(npatch, init='invalid')
    with assert_raises(ValueError):
        field.kmeans_initialize_centers(npatch=ngal*2, init='random')
    with assert_raises(ValueError):
        field.kmeans_initialize_centers(npatch=ngal+1, init='random')
    with assert_raises(ValueError):
        field.kmeans_initialize_centers(npatch=0, init='random')
    with assert_raises(ValueError):
        field.kmeans_initialize_centers(npatch=-100, init='random')

    # Should be valid to give npatch = 1, although not particularly useful.
    cen_1 = field.kmeans_initialize_centers(npatch=1, init='random')
    p_1 = field.kmeans_assign_patches(cen_1)
    np.testing.assert_equal(p_1, np.zeros(ngal))

    # If same number of patches as galaxies, each galaxy gets a patch.
    # (This is stupid of course, but check that it doesn't fail.)
    # Do this with fewer points though, since it's not particularly fast with N=10^5.
    n = 100
    cat = treecorr.Catalog(ra=ra[:n], dec=dec[:n], ra_units='rad', dec_units='rad')
    field = cat.getNField()
    cen_n = field.kmeans_initialize_centers(npatch=n, init='random')
    p_n = field.kmeans_assign_patches(cen_n)
    np.testing.assert_equal(sorted(p_n), list(range(n)))


def test_init_kmpp():
    # Test the init=random option

    ngal = 100000
    s = 1.
    rng = np.random.RandomState(8675309)
    x = rng.normal(0,s, (ngal,) )
    y = rng.normal(0,s, (ngal,) )
    z = rng.normal(0,s, (ngal,) )
    cat = treecorr.Catalog(x=x, y=y, z=z)
    xyz = np.array([x, y, z]).T

    # Skip the refine_centers step.
    print('3d with init=kmeans++')
    npatch = 10
    field = cat.getNField()
    cen1 = field.kmeans_initialize_centers(npatch, 'kmeans++')
    #print('cen = ',cen1)
    assert cen1.shape == (npatch, 3)
    p1 = field.kmeans_assign_patches(cen1)
    print('patches = ',np.unique(p1))
    assert len(p1) == cat.ntot
    assert min(p1) == 0
    assert max(p1) == npatch-1

    inertia1 = np.array([np.sum((xyz[p1==i] - cen1[i])**2) for i in range(npatch)])
    counts1 = np.array([np.sum(p1==i) for i in range(npatch)])
    print('counts = ',counts1)
    print('rms counts = ',np.std(counts1))
    print('total inertia = ',np.sum(inertia1))

    # Now run the normal way
    # Use higher max_iter, since random isn't a great initialization.
    p2 = field.run_kmeans(npatch, init='kmeans++', max_iter=1000)
    cen2 = np.array([xyz[p2==i].mean(axis=0) for i in range(npatch)])
    inertia2 = np.array([np.sum((xyz[p2==i] - cen2[i])**2) for i in range(npatch)])
    counts2 = np.array([np.sum(p2==i) for i in range(npatch)])
    print('rms counts => ',np.std(counts2))
    print('total inertia => ',np.sum(inertia2))
    assert np.sum(inertia2) < np.sum(inertia1)

    # Use a field with lots of top level cells
    print('3d with init=kmeans++, min_top=10')
    field = cat.getNField(min_top=10)
    cen1 = field.kmeans_initialize_centers(npatch, 'kmeans++')
    #print('cen = ',cen1)
    assert cen1.shape == (npatch, 3)
    p1 = field.kmeans_assign_patches(cen1)
    print('patches = ',np.unique(p1))
    assert len(p1) == cat.ntot
    assert min(p1) == 0
    assert max(p1) == npatch-1

    inertia1 = np.array([np.sum((xyz[p1==i] - cen1[i])**2) for i in range(npatch)])
    counts1 = np.array([np.sum(p1==i) for i in range(npatch)])
    print('counts = ',counts1)
    print('rms counts = ',np.std(counts1))
    print('total inertia = ',np.sum(inertia1))

    # Now run the normal way
    p2 = field.run_kmeans(npatch, init='kmeans++', max_iter=1000)
    cen2 = np.array([xyz[p2==i].mean(axis=0) for i in range(npatch)])
    inertia2 = np.array([np.sum((xyz[p2==i] - cen2[i])**2) for i in range(npatch)])
    counts2 = np.array([np.sum(p2==i) for i in range(npatch)])
    print('rms counts => ',np.std(counts2))
    print('total inertia => ',np.sum(inertia2))
    assert np.sum(inertia2) < np.sum(inertia1)

    # Repeat in 2d
    print('2d with init=kmeans++')
    cat = treecorr.Catalog(x=x, y=y)
    xy = np.array([x, y]).T
    field = cat.getNField()
    cen1 = field.kmeans_initialize_centers(npatch, 'kmeans++')
    #print('cen = ',cen1)
    assert cen1.shape == (npatch, 2)
    p1 = field.kmeans_assign_patches(cen1)
    print('patches = ',np.unique(p1))
    assert len(p1) == cat.ntot
    assert min(p1) == 0
    assert max(p1) == npatch-1

    inertia1 = np.array([np.sum((xy[p1==i] - cen1[i])**2) for i in range(npatch)])
    counts1 = np.array([np.sum(p1==i) for i in range(npatch)])
    print('counts = ',counts1)
    print('rms counts = ',np.std(counts1))
    print('total inertia = ',np.sum(inertia1))

    # Now run the normal way
    p2 = field.run_kmeans(npatch, init='kmeans++', max_iter=1000)
    cen2 = np.array([xy[p2==i].mean(axis=0) for i in range(npatch)])
    inertia2 = np.array([np.sum((xy[p2==i] - cen2[i])**2) for i in range(npatch)])
    counts2 = np.array([np.sum(p2==i) for i in range(npatch)])
    print('rms counts => ',np.std(counts2))
    print('total inertia => ',np.sum(inertia2))
    assert np.sum(inertia2) < np.sum(inertia1)

    # Repeat in spherical
    print('spher with init=kmeans++')
    ra, dec = coord.CelestialCoord.xyz_to_radec(x,y,z)
    cat = treecorr.Catalog(ra=ra, dec=dec, ra_units='rad', dec_units='rad')
    xyz = np.array([cat.x, cat.y, cat.z]).T
    field = cat.getNField()
    cen1 = field.kmeans_initialize_centers(npatch, 'kmeans++')
    #print('cen = ',cen1)
    assert cen1.shape == (npatch, 3)
    p1 = field.kmeans_assign_patches(cen1)
    print('patches = ',np.unique(p1))
    assert len(p1) == cat.ntot
    assert min(p1) == 0
    assert max(p1) == npatch-1

    inertia1 = np.array([np.sum((xyz[p1==i] - cen1[i])**2) for i in range(npatch)])
    counts1 = np.array([np.sum(p1==i) for i in range(npatch)])
    print('counts = ',counts1)
    print('rms counts = ',np.std(counts1))
    print('total inertia = ',np.sum(inertia1))

    # Now run the normal way
    p2 = field.run_kmeans(npatch, init='kmeans++', max_iter=1000)
    cen2 = np.array([xyz[p2==i].mean(axis=0) for i in range(npatch)])
    inertia2 = np.array([np.sum((xyz[p2==i] - cen2[i])**2) for i in range(npatch)])
    counts2 = np.array([np.sum(p2==i) for i in range(npatch)])
    print('rms counts => ',np.std(counts2))
    print('total inertia => ',np.sum(inertia2))
    assert np.sum(inertia2) < np.sum(inertia1)

    with assert_raises(ValueError):
        field.kmeans_initialize_centers(npatch=ngal*2, init='kmeans++')
    with assert_raises(ValueError):
        field.kmeans_initialize_centers(npatch=ngal+1, init='kmeans++')
    with assert_raises(ValueError):
        field.kmeans_initialize_centers(npatch=0, init='kmeans++')
    with assert_raises(ValueError):
        field.kmeans_initialize_centers(npatch=-100, init='kmeans++')

    # Should be valid to give npatch = 1, although not particularly useful.
    cen_1 = field.kmeans_initialize_centers(npatch=1, init='kmeans++')
    p_1 = field.kmeans_assign_patches(cen_1)
    np.testing.assert_equal(p_1, np.zeros(ngal))

    # If same number of patches as galaxies, each galaxy gets a patch.
    # (This is stupid of course, but check that it doesn't fail.)
    # Do this with fewer points though, since it's not particularly fast with N=10^5.
    n = 100
    cat = treecorr.Catalog(ra=ra[:n], dec=dec[:n], ra_units='rad', dec_units='rad')
    field = cat.getNField()
    cen_n = field.kmeans_initialize_centers(npatch=n, init='kmeans++')
    p_n = field.kmeans_assign_patches(cen_n)
    np.testing.assert_equal(sorted(p_n), list(range(n)))


if __name__ == '__main__':
    test_dessv()
    test_radec()
    test_3d()
    test_2d()
    test_init_random()
    test_init_kmpp()