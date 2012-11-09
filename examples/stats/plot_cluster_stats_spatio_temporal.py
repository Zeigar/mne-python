"""
====================================================================
Permutation t-test on source data with 2D spatio-temporal clustering
====================================================================

Tests if the evoked response is significantly different between
conditions across subjects (simulated here using one subject's data).
The multiple comparisons problem is adressed with a cluster-level
permutation test across space and time.

"""

# Authors: Alexandre Gramfort <gramfort@nmr.mgh.harvard.edu>
#          Eric Larson <larson.eric.d@gmail.com>
# License: BSD (3-clause)

print __doc__

import mne
from mne import fiff, spatio_temporal_tris_connectivity, compute_morph_matrix,\
                grade_to_tris, equalize_epoch_counts, SourceEstimate
from mne.stats import spatio_temporal_cluster_1samp_test
from mne.minimum_norm import apply_inverse, read_inverse_operator
from mne.datasets import sample
import os.path as op
import numpy as np
from numpy.random import randn
from scipy import stats as spstats

###############################################################################
# Set parameters
data_path = sample.data_path('..')
raw_fname = data_path + '/MEG/sample/sample_audvis_filt-0-40_raw.fif'
event_fname = data_path + '/MEG/sample/sample_audvis_filt-0-40_raw-eve.fif'
tmin = -0.2
tmax = 0.5

#   Setup for reading the raw data
raw = fiff.Raw(raw_fname)
events = mne.read_events(event_fname)

###############################################################################
# Read epochs for the channel of interest
picks = fiff.pick_types(raw.info, meg=True, eog=True)
event_id = 1  # L auditory
reject = dict(grad=4000e-13, eog=150e-6)
epochs1 = mne.Epochs(raw, events, event_id, tmin, tmax, picks=picks,
                     baseline=(None, 0), reject=reject, preload=True)

event_id = 3  # R visual
epochs2 = mne.Epochs(raw, events, event_id, tmin, tmax, picks=picks,
                     baseline=(None, 0), reject=reject, preload=True)

#    Equalize trial counts to eliminate bias (which would otherwise be
#    introduced by the abs() performed below)
equalize_epoch_counts(epochs1, epochs2)

###############################################################################
# Transform to source space

fname_inv = data_path + '/MEG/sample/sample_audvis-meg-oct-6-meg-inv.fif'
snr = 3.0
lambda2 = 1.0 / snr ** 2
method = "dSPM"  # use dSPM method (could also be MNE or sLORETA)
inverse_operator = read_inverse_operator(fname_inv)
sample_vertices = [s['vertno'] for s in inverse_operator['src']]

#    Let's average, resample for speed purposes, and then compute inverse
evoked1 = epochs1.average()
evoked1.resample(100)
condition1 = apply_inverse(evoked1, inverse_operator, lambda2, method)
evoked2 = epochs2.average()
evoked2.resample(100)
condition2 = apply_inverse(evoked2, inverse_operator, lambda2, method)

#    Let's only deal with 0 < t 0.4, cropping to reduce multiple comparisons
condition1.crop(0, 0.4)
condition2.crop(0, 0.4)
tmin = condition1.tmin
tstep = condition1.tstep
times = condition1.times

###############################################################################
# Transform to common cortical space

#    Normally you would read in estimates across several subjects on the same
#    cortical space (e.g. fsaverage), but we'll just simulate that each subject
#    has the same response (just noisy) here
condition1 = condition1.data
condition2 = condition2.data
n_simulate = 8
noise_level = 3  # this is a reasonable choice here
X1 = randn(condition1.shape[0], condition1.shape[1], n_simulate) * noise_level
X2 = randn(condition2.shape[0], condition2.shape[1], n_simulate) * noise_level
for ri in range(n_simulate):
    X1[:, :, ri] += condition1
    X2[:, :, ri] += condition2
del condition1
del condition2

#    It's a good idea to spatially smooth the data, and for visualization
#    purposes, let's morph these to fsaverage, which is a grade 5 source space
#    with vertices 0:10242 for each hemisphere. Usually you'd have to morph
#    each subject's data separately (and you might want to use morph_data
#    instead), but here since all estimates are on 'sample'we can use one
#    morph matix for all the heavy lifting.
fsave_vertices = [np.arange(10242), np.arange(10242)]
morph_mat = compute_morph_matrix('sample', 'fsaverage', sample_vertices,
                                 fsave_vertices, 20,
                                 op.join(data_path, 'subjects'), array=True
#    We have to swap axes for the dot() to work properly
X1 = np.swapaxes(X1, 0, 1)
X2 = np.swapaxes(X2, 0, 1)
X1 = np.dot(morph_mat, X1)
X2 = np.dot(morph_mat, X2)
raise ValueError('me')

#    We want to compare the overall activity levels in each condition
X = abs(X1) - abs(X2)
del X1
del X2

###############################################################################
# Compute statistic

#    To use an algorithm optimized for spatio-temporal clutering, we
#    use n_times=1 even though there are ~100 time points in the data
connectivity = spatio_temporal_tris_connectivity(grade_to_tris(5), n_times=1)

#    Note that X needs to be a multi-dimensional array of shape
#    samples (subjects) x space x time, so we permute dimensions
X = np.transpose(X, [2, 0, 1])

#    Now let's actually do the clustering (can be slow!), making it faster here
#    by being more conservative for which points to cluster (higher threshold)
threshold = np.inf  # -spstats.distributions.t.ppf(0.001, n_simulate)
T_obs, clusters, cluster_p_values, H0 = \
    spatio_temporal_cluster_1samp_test(X, connectivity=connectivity, n_jobs=2,
                                       n_permutations=1, threshold=threshold,
                                       check_disjoint=True)

stc = SourceEstimate(T_obs, vertices=fsave_vertices, tmin=tmin, tstep=tstep)
raise ValueError('me')
###############################################################################
# Plot
times = epochs1.times
import pylab as pl
pl.close('all')
pl.subplot(211)
pl.title('Channel : ' + channel)
pl.plot(times, condition1.mean(axis=0) - condition2.mean(axis=0),
        label="ERF Contrast (Event 1 - Event 2)")
pl.ylabel("MEG (T / m)")
pl.legend()
pl.subplot(212)
for i_c, c in enumerate(clusters):
    c = c[0]
    if cluster_p_values[i_c] <= 0.05:
        h = pl.axvspan(times[c.start], times[c.stop - 1], color='r', alpha=0.3)
    else:
        pl.axvspan(times[c.start], times[c.stop - 1], color=(0.3, 0.3, 0.3),
                   alpha=0.3)
hf = pl.plot(times, T_obs, 'g')
pl.legend((h, ), ('cluster p-value < 0.05', ))
pl.xlabel("time (ms)")
pl.ylabel("f-values")
pl.show()
