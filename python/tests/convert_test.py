# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2021 Scipp contributors (https://github.com/scipp)
# @author Jan-Lukas Wynen

import itertools

import pytest
import scipp as sc
import scippneutron as scn


def make_beamline_dataset():
    dset = sc.Dataset()
    dset.coords['source_position'] = sc.vector(value=[0.0, 0.0, -10.0],
                                               unit='m')
    dset.coords['sample_position'] = sc.vector(value=[0.0, 0.0, 0.0], unit='m')
    dset.coords['position'] = sc.vectors(dims=['spectrum'],
                                         values=[[1.0, 0.0, 0.0],
                                                 [0.1, 0.0, 1.0]],
                                         unit='m')
    return dset


def make_tof_dataset():
    dset = make_beamline_dataset()
    dset['counts'] = sc.arange('x', 1, 7,
                               unit='counts').fold('x', {
                                   'spectrum': 2,
                                   'tof': 3
                               })
    dset.coords['tof'] = sc.array(dims=['tof'],
                                  values=[4000.0, 5000.0, 6100.0, 7300.0],
                                  unit='us')
    return dset


def make_count_density_variable(unit):
    return sc.arange('x', 1.0, 7.0,
                     unit=sc.units.counts / unit).fold('x', {
                         'spectrum': 2,
                         'tof': 3
                     })


def test_convert_input_unchanged():
    inputs = make_tof_dataset()
    original = inputs.copy(deep=True)
    result = scn.convert(inputs,
                         origin='tof',
                         target='wavelength',
                         scatter=True)
    assert not sc.identical(result, original)
    assert sc.identical(inputs, original)


TOF_TARGET_DIMS = ('dspacing', 'wavelength', 'energy')


@pytest.mark.parametrize('target', TOF_TARGET_DIMS)
def test_convert_slice(target):
    tof = make_tof_dataset()
    expected = scn.convert(tof['counts'],
                           origin='tof',
                           target=target,
                           scatter=True)['spectrum', 0].copy()
    # A side-effect of `convert` is that it turns relevant meta data into
    # coords or attrs, depending on the target unit. Slicing (without range)
    # turns coords into attrs, but applying `convert` effectively reverses
    # this, which is why we have this slightly unusual behavior here:
    if target != 'dspacing':
        expected.coords['position'] = expected.attrs.pop('position')
    assert sc.identical(
        scn.convert(tof['counts']['spectrum', 0].copy(),
                    origin='tof',
                    target=target,
                    scatter=True), expected)
    # Converting slice of item is same as item of converted slice
    assert sc.identical(
        scn.convert(tof['counts']['spectrum', 0].copy(),
                    origin='tof',
                    target=target,
                    scatter=True).data,
        scn.convert(tof['spectrum', 0].copy(),
                    origin='tof',
                    target=target,
                    scatter=True)['counts'].data)


@pytest.mark.parametrize('target', TOF_TARGET_DIMS)
def test_convert_fail_count_density(target):
    tof = make_tof_dataset()
    # conversion with plain counts works
    converted = scn.convert(tof, origin='tof', target=target, scatter=True)
    scn.convert(converted, origin=target, target='tof', scatter=True)

    tof[''] = make_count_density_variable(tof.coords['tof'].unit)
    converted[''] = make_count_density_variable(converted.coords[target].unit)
    # conversion with count densities fails
    with pytest.raises(sc.UnitError):
        scn.convert(tof, origin='tof', target=target, scatter=True)
    with pytest.raises(sc.UnitError):
        scn.convert(converted, origin=target, target='tof', scatter=True)


def test_convert_scattering_conversion_fails_with_noscatter_mode():
    tof = make_tof_dataset()
    scn.convert(tof, origin='tof', target='dspacing',
                scatter=True)  # no exception
    with pytest.raises(RuntimeError):
        scn.convert(tof, origin='tof', target='dspacing', scatter=False)

    wavelength = scn.convert(tof,
                             origin='tof',
                             target='wavelength',
                             scatter=True)
    scn.convert(wavelength, origin='wavelength', target='Q', scatter=True)
    with pytest.raises(RuntimeError):
        scn.convert(wavelength, origin='wavelength', target='Q', scatter=False)


def make_dataset_in(dim):
    if dim == 'tof':
        return make_tof_dataset()  # TODO triggers segfault otherwise
    return scn.convert(make_tof_dataset(),
                       origin='tof',
                       target=dim,
                       scatter=True)


@pytest.mark.parametrize(('origin', 'target'),
                         itertools.product(
                             ('tof', 'dspacing', 'wavelength', 'energy'),
                             repeat=2))
def test_convert_dataset_vs_dataarray(origin, target):
    if target == 'tof' and origin == 'tof':
        return  # TODO triggers segfault otherwise
    inputs = make_dataset_in(origin)
    expected = scn.convert(inputs, origin=origin, target=target, scatter=True)
    result = sc.Dataset(
        data={
            name: scn.convert(
                data.copy(), origin=origin, target=target, scatter=True)
            for name, data in inputs.items()
        })
    for name, data in result.items():
        assert sc.identical(data, expected[name])
