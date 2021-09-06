# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2021 Scipp contributors (https://github.com/scipp)
# @author Jan-Lukas Wynen

import math

import numpy as np
import pytest
import scipp as sc
from scipp.constants import m_n
import scippneutron as scn


def make_source_position():
    return sc.vector(value=[0.0, 0.0, -10.0], unit='m')


def make_sample_position():
    # Test assume that the sample is in the origin.
    return sc.vector(value=[0.0, 0.0, 0.0], unit='m')


def make_position():
    return sc.vectors(dims=['spectrum'],
                      values=[[1.0, 0.0, 0.0], [0.1, 0.0, 1.0]],
                      unit='m')


def make_incident_beam():
    return sc.vector(value=[0.0, 0.0, 10.0], unit='m')


def make_scattered_beam():
    return sc.vectors(dims=['spectrum'],
                      values=[[1.0, 0.0, 0.0], [0.1, 0.0, 1.0]],
                      unit='m')


def make_L1():
    return sc.norm(make_incident_beam())


def make_L2():
    return sc.norm(make_scattered_beam())


def make_Ltotal():
    return make_L1() + make_L2()


def make_two_theta():
    return sc.acos(
        sc.array(dims=['spectrum'], values=[0, 10], unit='m^2') / make_L1() / make_L2())


def make_tof():
    return sc.array(dims=['tof'], values=[4000.0, 5000.0, 6100.0, 7300.0], unit='us')


_COORD_MAKERS = {
    'source_position': make_source_position,
    'sample_position': make_sample_position,
    'position': make_position,
    'incident_beam': make_incident_beam,
    'scattered_beam': make_scattered_beam,
    'L1': make_L1,
    'L2': make_L2,
    'Ltotal': make_Ltotal,
    'two_theta': make_two_theta,
    'tof': make_tof
}


def make_test_data(coords=(), dataset=False):
    da = sc.DataArray(
        sc.arange('x', 1, 7, unit='counts').fold('x', {
            'spectrum': 2,
            'tof': 3
        }))
    for name, maker in _COORD_MAKERS.items():
        if name in coords:
            da.coords[name] = maker()

    if dataset:
        return sc.Dataset(data={'counts': da})
    return da


def make_tof_binned_events():
    buffer = sc.DataArray(
        sc.zeros(dims=['event'], shape=[7], dtype=float),
        coords={
            'tof':
            sc.array(dims=['event'],
                     values=[1000.0, 3000.0, 2000.0, 4000.0, 5000.0, 6000.0, 3000.0],
                     unit='us')
        })
    return sc.bins(data=buffer,
                   dim='event',
                   begin=sc.array(dims=['spectrum'], values=[0, 4]),
                   end=sc.array(dims=['spectrum'], values=[4, 7]))


def make_count_density_variable(unit):
    return sc.arange('x', 1.0, 7.0,
                     unit=sc.units.counts / unit).fold('x', {
                         'spectrum': 2,
                         'tof': 3
                     })


def check_tof_conversion_metadata(converted, target, coord_unit):
    assert 'tof' not in converted.coords
    assert target in converted.coords
    assert 'counts' in converted
    assert converted['counts'].sizes == {'spectrum': 2, target: 3}
    assert converted['counts'].unit == sc.units.counts
    np.testing.assert_array_equal(converted['counts'].values.flat, np.arange(1, 7))

    coord = converted.coords[target]
    # Due to conversion, the coordinate now also depends on 'spectrum'.
    assert coord.sizes == {'spectrum': 2, target: 4}
    assert coord.unit == coord_unit


def make_dataset_in(dim):
    tof_dset = make_test_data(coords=('tof', 'Ltotal', 'two_theta'), dataset=True)
    if dim == 'tof':
        return tof_dset  # TODO triggers segfault otherwise
    return scn.convert(tof_dset, origin='tof', target=dim, scatter=True)


@pytest.mark.parametrize(
    ('origin', 'target'),
    (('tof', 'dspacing'), ('tof', 'wavelength'), ('tof', 'energy')))
def test_convert_dataset_vs_dataarray(origin, target):
    if target == 'tof' and origin == 'tof':
        return  # TODO triggers segfault otherwise
    inputs = make_dataset_in(origin)
    expected = scn.convert(inputs, origin=origin, target=target, scatter=True)
    result = sc.Dataset(
        data={
            name: scn.convert(data.copy(), origin=origin, target=target, scatter=True)
            for name, data in inputs.items()
        })
    for name, data in result.items():
        assert sc.identical(data, expected[name])


def test_convert_input_unchanged():
    inputs = make_test_data(coords=('tof', 'Ltotal'), dataset=True)
    original = inputs.copy(deep=True)
    result = scn.convert(inputs, origin='tof', target='wavelength', scatter=True)
    assert not sc.identical(result, original)
    assert sc.identical(inputs, original)


TOF_TARGET_DIMS = ('dspacing', 'wavelength', 'energy')


@pytest.mark.parametrize('target', TOF_TARGET_DIMS)
def test_convert_slice(target):
    tof = make_test_data(coords=('tof', 'Ltotal', 'two_theta'), dataset=True)
    expected = scn.convert(tof['counts'], origin='tof', target=target,
                           scatter=True)['spectrum', 0].copy()
    # A side-effect of `convert` is that it turns relevant meta data into
    # coords or attrs, depending on the target unit. Slicing (without range)
    # turns coords into attrs, but applying `convert` effectively reverses
    # this, which is why we have this slightly unusual behavior here:
    if target != 'dspacing':
        expected.coords['two_theta'] = expected.attrs.pop('two_theta')
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


def test_convert_scattering_conversion_fails_with_noscatter_mode():
    tof = make_test_data(coords=('tof', 'Ltotal', 'two_theta'), dataset=True)
    scn.convert(tof, origin='tof', target='dspacing', scatter=True)  # no exception
    with pytest.raises(RuntimeError):
        scn.convert(tof, origin='tof', target='dspacing', scatter=False)

    wavelength = scn.convert(tof, origin='tof', target='wavelength', scatter=True)
    scn.convert(wavelength, origin='wavelength', target='Q', scatter=True)
    with pytest.raises(RuntimeError):
        scn.convert(wavelength, origin='wavelength', target='Q', scatter=False)


def test_convert_coords_vs_attributes():
    with_coords = make_test_data(coords=('tof', 'Ltotal', 'two_theta'), dataset=True)
    with_attrs = with_coords.copy()
    for key in ('sample_position', 'source_position', 'position'):
        with_attrs['counts'].attrs[key] = with_attrs.coords.pop(key)

    from_coords = scn.convert(with_coords,
                              origin='tof',
                              target='wavelength',
                              scatter=True)
    from_attrs = scn.convert(with_attrs,
                             origin='tof',
                             target='wavelength',
                             scatter=True)
    assert sc.identical(from_coords, from_attrs)


@pytest.mark.parametrize('target', ('incident_beam', 'scattered_beam'))
def test_convert_beams(target):
    # A single sample position.
    original = make_test_data(coords=('position', 'sample_position', 'source_position'))
    converted = scn.convert(original, origin='position', target=target, scatter=True)
    for key in ('position', 'source_position', 'sample_position'):
        assert key not in converted.coords
    assert sc.identical(converted.coords['incident_beam'], make_incident_beam())
    assert sc.identical(converted.coords['scattered_beam'], make_scattered_beam())

    # Two sample positions.
    original = make_test_data(coords=('position', 'source_position'))
    original.coords['sample_position'] = sc.vectors(dims=['spectrum'],
                                                    values=[[1.0, 0.0, 0.2],
                                                            [2.1, -0.3, 1.4]],
                                                    unit='m')
    converted = scn.convert(original, origin='position', target=target, scatter=True)
    for key in ('position', 'source_position', 'sample_position'):
        assert key not in converted.coords
    assert sc.allclose(converted.coords['incident_beam'],
                       sc.vectors(dims=['spectrum'],
                                  values=[[1.0, 0.0, 10.2], [2.1, -0.3, 11.4]],
                                  unit='m'),
                       rtol=1e-14 * sc.units.one)
    assert sc.allclose(converted.coords['scattered_beam'],
                       sc.vectors(dims=['spectrum'],
                                  values=[[0.0, 0.0, -0.2], [-2.0, 0.3, -0.4]],
                                  unit='m'),
                       rtol=1e-14 * sc.units.one)


@pytest.mark.parametrize('target', ('L1', 'L2', 'two_theta', 'Ltotal'))
def test_convert_beam_length_and_angle(target):
    original = make_test_data(coords=('incident_beam', 'scattered_beam'))
    L1 = make_L1()
    L2 = make_L2()
    two_theta = make_two_theta()

    converted = scn.convert(original, origin='position', target=target, scatter=True)
    assert sc.identical(converted.meta['L1'], L1)
    assert sc.identical(converted.meta['L2'], L2)
    assert sc.identical(converted.meta['two_theta'], two_theta)
    if target == 'Ltotal':
        assert sc.identical(converted.coords['Ltotal'], L1 + L2)


def test_convert_tof_to_dspacing():
    tof = make_test_data(coords=('tof', 'Ltotal', 'two_theta'), dataset=True)
    dspacing = scn.convert(tof, origin='tof', target='dspacing', scatter=True)
    check_tof_conversion_metadata(dspacing, 'dspacing', sc.units.angstrom)

    # Rule of thumb (https://www.psi.ch/niag/neutron-physics):
    # v [m/s] = 3956 / \lambda [ Angstrom ]
    tof_in_seconds = tof.coords['tof'] * 1e-6

    # Spectrum 0 is 11 m from source
    # 2d sin(theta) = n \lambda
    # theta = 45 deg => d = lambda / (2 * 1 / sqrt(2))
    for val, t in zip(dspacing.coords['dspacing']['spectrum', 0].values,
                      tof_in_seconds.values):
        np.testing.assert_almost_equal(val, 3956.0 / (11.0 / t) / math.sqrt(2.0),
                                       val * 1e-3)

    # Spectrum 1
    # sin(2 theta) = 0.1/(L-10)
    L = 10.0 + math.sqrt(1.0 * 1.0 + 0.1 * 0.1)
    lambda_to_d = 1.0 / (2.0 * math.sin(0.5 * math.asin(0.1 / (L - 10.0))))
    for val, t in zip(dspacing.coords['dspacing']['spectrum', 1].values,
                      tof_in_seconds.values):
        np.testing.assert_almost_equal(val, 3956.0 / (L / t) * lambda_to_d, val * 1e-3)


def test_convert_tof_to_wavelength():
    tof = make_test_data(coords=('tof', 'Ltotal'), dataset=True)
    wavelength = scn.convert(tof, origin='tof', target='wavelength', scatter=True)
    check_tof_conversion_metadata(wavelength, 'wavelength', sc.units.angstrom)

    # Rule of thumb (https://www.psi.ch/niag/neutron-physics):
    # v [m/s] = 3956 / \lambda [ Angstrom ]
    tof_in_seconds = tof.coords['tof'] * 1e-6

    # Spectrum 0 is 11 m from source
    for val, t in zip(wavelength.coords['wavelength']['spectrum', 0].values,
                      tof_in_seconds.values):
        np.testing.assert_almost_equal(val, 3956.0 / (11.0 / t), val * 1e-3)
    # Spectrum 1
    L = 10.0 + math.sqrt(1.0 * 1.0 + 0.1 * 0.1)
    for val, t in zip(wavelength.coords['wavelength']['spectrum', 1].values,
                      tof_in_seconds.values):
        np.testing.assert_almost_equal(val, 3956.0 / (L / t), val * 1e-3)


def test_convert_tof_to_Q():
    tof = make_test_data(coords=('tof', 'Ltotal', 'two_theta'), dataset=True)
    wavelength = scn.convert(tof, origin='tof', target='wavelength', scatter=True)
    Q_from_tof = scn.convert(tof, origin='tof', target='Q', scatter=True)
    Q_from_wavelength = scn.convert(wavelength,
                                    origin='wavelength',
                                    target='Q',
                                    scatter=True)
    check_tof_conversion_metadata(Q_from_tof, 'Q', sc.units.one / sc.units.angstrom)
    check_tof_conversion_metadata(Q_from_wavelength, 'Q',
                                  sc.units.one / sc.units.angstrom)
    # wavelength is intermediate in this case and thus kept but not in the other case.
    del Q_from_tof['counts'].attrs['wavelength']
    assert sc.identical(Q_from_tof, Q_from_wavelength)

    # Rule of thumb (c):
    # v [m/s] = 3956 / \lambda [ Angstrom ]
    tof_in_seconds = tof.coords['tof'] * 1e-6

    # Spectrum 0 is 11 m from source
    # Q = 4pi sin(theta) / lambda
    # theta = 45 deg => Q = 2 sqrt(2) pi / lambda
    for val, t in zip(Q_from_wavelength.coords['Q']['spectrum', 0].values,
                      tof_in_seconds.values):
        np.testing.assert_almost_equal(
            val, 2.0 * math.sqrt(2.0) * math.pi / (3956.0 / (11.0 / t)), val * 1e-3)

    # Spectrum 1
    # sin(2 theta) = 0.1/(L-10)
    L = 10.0 + math.sqrt(1.0 * 1.0 + 0.1 * 0.1)
    lambda_to_Q = 4.0 * math.pi * math.sin(math.asin(0.1 / (L - 10.0)) / 2.0)
    for val, t in zip(Q_from_wavelength.coords['Q']['spectrum', 1].values,
                      tof_in_seconds.values):
        np.testing.assert_almost_equal(val, lambda_to_Q / (3956.0 / (L / t)),
                                       val * 1e-3)


def test_convert_tof_to_energy_elastic():
    tof = make_test_data(coords=('tof', 'Ltotal'), dataset=True)
    energy = scn.convert(tof, origin='tof', target='energy', scatter=True)
    check_tof_conversion_metadata(energy, 'energy', sc.units.meV)

    tof_in_seconds = sc.to_unit(tof.coords['tof'], 's')
    # e [J] = 1/2 m(n) [kg] (l [m] / tof [s])^2
    joule_to_mev = sc.to_unit(1.0 * sc.Unit('J'), sc.units.meV).value
    neutron_mass = sc.to_unit(m_n, sc.units.kg).value

    # Spectrum 0 is 11 m from source
    for val, t in zip(energy.coords['energy']['spectrum', 0].values,
                      tof_in_seconds.values):
        np.testing.assert_almost_equal(val,
                                       joule_to_mev * neutron_mass / 2 * (11 / t)**2,
                                       val * 1e-3)
    # Spectrum 1
    L = 10.0 + math.sqrt(1.0 * 1.0 + 0.1 * 0.1)
    for val, t in zip(energy.coords['energy']['spectrum', 1].values,
                      tof_in_seconds.values):
        np.testing.assert_almost_equal(val,
                                       joule_to_mev * 0.5 * neutron_mass * (L / t)**2,
                                       val * 1e-3)


def test_convert_tof_to_energy_elastic_fails_if_inelastic_params_present():
    # Note these conversion fail only because they are not implemented.
    # It should definitely be possible to support this.
    tof = make_test_data(coords=('tof', 'L1', 'L2'), dataset=True)
    scn.convert(tof, origin='tof', target='energy', scatter=True)
    tof.coords['incident_energy'] = 2.1 * sc.units.meV
    with pytest.raises(RuntimeError):
        scn.convert(tof, origin='tof', target='energy', scatter=True)

    del tof.coords['incident_energy']
    scn.convert(tof, origin='tof', target='energy', scatter=True)
    tof.coords['final_energy'] = 2.1 * sc.units.meV
    with pytest.raises(RuntimeError):
        scn.convert(tof, origin='tof', target='energy', scatter=True)


def test_convert_tof_to_energy_transfer_direct():
    tof = make_test_data(coords=('tof', 'L1', 'L2'), dataset=True)
    with pytest.raises(RuntimeError):
        scn.convert(tof, origin='tof', target='energy_transfer', scatter=True)
    tof.coords['incident_energy'] = 35.0 * sc.units.meV
    direct = scn.convert(tof, origin='tof', target='energy_transfer', scatter=True)
    assert 'energy_transfer' in direct.coords
    assert 'tof' not in direct.coords
    tof_direct = scn.convert(direct,
                             origin='energy_transfer',
                             target='tof',
                             scatter=True)
    assert sc.all(
        sc.isclose(tof_direct.coords['tof'],
                   tof.coords['tof'],
                   rtol=0.0 * sc.units.one,
                   atol=1e-11 * sc.units.us)).value
    tof_direct.coords['tof'] = tof.coords['tof']
    assert sc.identical(tof_direct, tof)


def test_convert_tof_to_energy_transfer_indirect():
    tof = make_test_data(coords=('tof', 'L1', 'L2'), dataset=True)
    with pytest.raises(RuntimeError):
        scn.convert(tof, origin='tof', target='energy_transfer', scatter=True)
    tof.coords['incident_energy'] = 25.0 * sc.units.meV
    tof.coords['final_energy'] = 35.0 * sc.units.meV
    with pytest.raises(RuntimeError):
        scn.convert(tof, origin='tof', target='energy_transfer', scatter=True)
    del tof.coords['incident_energy']
    indirect = scn.convert(tof, origin='tof', target='energy_transfer', scatter=True)
    assert 'energy_transfer' in indirect.coords
    assert 'tof' not in indirect.coords
    tof_indirect = scn.convert(indirect,
                               origin='energy_transfer',
                               target='tof',
                               scatter=True)
    assert sc.all(
        sc.isclose(tof_indirect.coords['tof'],
                   tof.coords['tof'],
                   rtol=0.0 * sc.units.one,
                   atol=1e-11 * sc.units.us)).value
    tof_indirect.coords['tof'] = tof.coords['tof']
    assert sc.identical(tof_indirect, tof)


def test_convert_tof_to_energy_transfer_direct_indirect_are_distinct():
    tof_direct = make_test_data(coords=('tof', 'L1', 'L2'), dataset=True)
    tof_direct.coords['incident_energy'] = 22.0 * sc.units.meV
    direct = scn.convert(tof_direct,
                         origin='tof',
                         target='energy_transfer',
                         scatter=True)

    tof_indirect = make_test_data(coords=('tof', 'L1', 'L2'), dataset=True)
    tof_indirect.coords['final_energy'] = 22.0 * sc.units.meV
    indirect = scn.convert(tof_indirect,
                           origin='tof',
                           target='energy_transfer',
                           scatter=True)
    assert not sc.all(
        sc.isclose(direct.coords['energy_transfer'],
                   indirect.coords['energy_transfer'],
                   rtol=0.0 * sc.units.one,
                   atol=1e-11 * sc.units.meV)).value


@pytest.mark.parametrize('target', TOF_TARGET_DIMS)
def test_convert_with_factor_type_promotion(target):
    tof = make_test_data(coords=('Ltotal', 'two_theta'))
    tof.coords['tof'] = sc.array(dims=['tof'],
                                 values=[4000, 5000, 6100, 7300],
                                 unit='us',
                                 dtype='float32')
    res = scn.convert(tof, origin='tof', target=target, scatter=True)
    assert res.coords[target].dtype == sc.dtype.float32
    res = scn.convert(res, origin=target, target='tof', scatter=True)
    assert res.coords['tof'].dtype == sc.dtype.float32


@pytest.mark.parametrize('target', TOF_TARGET_DIMS)
def test_convert_binned_events_converted(target):
    tof = make_test_data(coords=('Ltotal', 'two_theta'), dataset=True)
    # Standard dense coord for comparison purposes. The final 0 is a dummy.
    tof.coords['tof'] = sc.array(dims=['spectrum', 'tof'],
                                 values=[[1000.0, 3000.0, 2000.0, 4000.0],
                                         [5000.0, 6000.0, 3000.0, 0.0]],
                                 unit='us')
    tof['events'] = make_tof_binned_events()
    original = tof.copy(deep=True)
    assert sc.identical(tof, original)

    res = scn.convert(tof, origin='tof', target=target, scatter=True)
    values = res['events'].values
    for bin_index in range(1):
        expected = res.coords[target]['spectrum',
                                      bin_index].rename_dims({target: 'event'})
        assert 'tof' not in values[bin_index].coords
        assert target in values[bin_index].coords
        assert sc.identical(values[bin_index].coords[target], expected)


@pytest.mark.parametrize('target', TOF_TARGET_DIMS)
def test_convert_binned_convert_slice(target):
    tof = make_test_data(coords=('tof', 'Ltotal', 'two_theta'))['tof', 0].copy()
    tof.data = make_tof_binned_events()
    original = tof.copy()
    full = scn.convert(tof, origin='tof', target=target, scatter=True)
    sliced = scn.convert(tof['spectrum', 1:2],
                         origin='tof',
                         target=target,
                         scatter=True)
    assert sc.identical(sliced, full['spectrum', 1:2])
    assert sc.identical(tof, original)
