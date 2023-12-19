# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2023 Scipp contributors (https://github.com/scipp)

import pytest
import scipp as sc
import scipp.constants
import scipp.testing
from numpy import pi

from scippneutron.chopper import DiskChopper, DiskChopperType


def deg_angle_to_time_factor(rotation_speed: float) -> float:
    # Multiply by the returned value to convert an angle in degrees
    # to the time when the point at the angle reaches tdc.
    to_rad = sc.constants.pi.value / 180
    angular_frequency = abs(rotation_speed) * (2 * sc.constants.pi.value)
    return to_rad / angular_frequency


@pytest.fixture
def nexus_chopper():
    return sc.DataGroup(
        {
            'type': DiskChopperType.single,
            'position': sc.vector([0.0, 0.0, 2.0], unit='m'),
            'rotation_speed': sc.scalar(12.0, unit='Hz'),
            'beam_position': sc.scalar(45.0, unit='deg'),
            'phase': sc.scalar(-20.0, unit='deg'),
            'slit_edges': sc.array(
                dims=['slit', 'edge'], values=[[0.0, 60.0], [124.0, 126.0]], unit='deg'
            ),
            'slit_height': sc.array(dims=['slit'], values=[0.4, 0.3], unit='m'),
            'radius': sc.scalar(0.5, unit='m'),
        }
    )


@pytest.mark.parametrize(
    'typ',
    (
        'contra_rotating_pair',
        'synchro_pair',
        DiskChopperType.contra_rotating_pair,
        DiskChopperType.synchro_pair,
    ),
)
def test_chopper_supports_only_single(nexus_chopper, typ):
    nexus_chopper['type'] = typ
    with pytest.raises(NotImplementedError):
        DiskChopper.from_nexus(nexus_chopper)


def test_rotation_speed_must_be_frequency(nexus_chopper):
    nexus_chopper['rotation_speed'] = sc.scalar(1.0, unit='m/s')
    with pytest.raises(sc.UnitError):
        DiskChopper.from_nexus(nexus_chopper)


def test_eq(nexus_chopper):
    ch1 = DiskChopper.from_nexus(nexus_chopper)
    ch2 = DiskChopper.from_nexus(nexus_chopper)
    assert ch1 == ch2


@pytest.mark.parametrize(
    'replacement',
    (
        ('rotation_speed', sc.scalar(13.0, unit='Hz')),
        ('position', sc.vector([1, 0, 0], unit='m')),
        ('radius', sc.scalar(1.0, unit='m')),
        ('phase', sc.scalar(15, unit='deg')),
        ('slit_height', sc.scalar(0.14, unit='cm')),
        ('slit_edges', sc.array(dims=['edge'], values=[0.1, 0.3], unit='rad')),
    ),
)
def test_neq(nexus_chopper, replacement):
    ch1 = DiskChopper.from_nexus(nexus_chopper)
    ch2 = DiskChopper.from_nexus({**nexus_chopper, replacement[0]: replacement[1]})
    assert ch1 != ch2


def test_slit_begin_end_no_slit(nexus_chopper):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'slit_edges': sc.zeros(sizes={'slit': 0, 'edge': 2}, unit='deg'),
        }
    )
    assert sc.identical(ch.slit_begin, sc.array(dims=['slit'], values=[], unit='deg'))
    assert sc.identical(ch.slit_end, sc.array(dims=['slit'], values=[], unit='deg'))


def test_slit_begin_end_one_slit(nexus_chopper):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'slit_edges': sc.array(
                dims=['slit', 'edge'], values=[[13, 43]], unit='deg'
            ),
        }
    )
    assert sc.identical(ch.slit_begin, sc.array(dims=['slit'], values=[13], unit='deg'))
    assert sc.identical(ch.slit_end, sc.array(dims=['slit'], values=[43], unit='deg'))


def test_slit_begin_end_two_slits(nexus_chopper):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'slit_edges': sc.array(
                dims=['slit', 'edge'], values=[[0, 60], [124, 126]], unit='deg'
            ),
        }
    )
    assert sc.identical(
        ch.slit_begin, sc.array(dims=['slit'], values=[0, 124], unit='deg')
    )
    assert sc.identical(
        ch.slit_end, sc.array(dims=['slit'], values=[60, 126], unit='deg')
    )


@pytest.mark.parametrize('rotation_speed', (1.0, -1.0))
def test_slit_begin_end_two_slits_unordered(nexus_chopper, rotation_speed):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'slit_edges': sc.array(
                dims=['slit', 'edge'], values=[[2.5, 2.8], [0.8, 1.3]], unit='rad'
            ),
        }
    )
    assert sc.identical(
        ch.slit_begin, sc.array(dims=['slit'], values=[2.5, 0.8], unit='rad')
    )
    assert sc.identical(
        ch.slit_end, sc.array(dims=['slit'], values=[2.8, 1.3], unit='rad')
    )


def test_slit_begin_end_across_0(nexus_chopper):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'slit_edges': sc.array(
                dims=['slit', 'edge'], values=[[340.0, 382.0]], unit='deg'
            ),
        }
    )
    assert sc.identical(
        ch.slit_begin, sc.array(dims=['slit'], values=[340.0], unit='deg')
    )
    assert sc.identical(
        ch.slit_end, sc.array(dims=['slit'], values=[382.0], unit='deg')
    )


@pytest.mark.parametrize('beam_position_unit', ('rad', 'deg'))
@pytest.mark.parametrize('phase_unit', ('rad', 'deg'))
def test_time_offset_angle_at_beam_no_phase_zero_beam_pos_clockwise_single_angle(
    nexus_chopper, beam_position_unit, phase_unit
):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'beam_position': sc.scalar(0.0, unit=beam_position_unit),
            'phase': sc.scalar(0.0, unit=phase_unit),
            'rotation_speed': sc.scalar(-2.3, unit='Hz'),
        }
    )
    omega = 2 * pi * 2.3
    sc.testing.assert_identical(
        ch.time_offset_angle_at_beam(angle=sc.scalar(0.0, unit='rad')),
        sc.scalar(0.0, unit='s'),
    )
    sc.testing.assert_identical(
        ch.time_offset_angle_at_beam(angle=sc.scalar(0.0, unit='deg')),
        sc.scalar(0.0, unit='s'),
    )
    sc.testing.assert_identical(
        ch.time_offset_angle_at_beam(angle=sc.scalar(1.2, unit='rad')),
        sc.scalar(1.2 / omega, unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(-0.4, unit='rad')),
        sc.scalar(-0.4 / omega, unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(7.1, unit='rad')),
        sc.scalar(7.1 / omega, unit='s'),
    )


@pytest.mark.parametrize('beam_position_unit', ('rad', 'deg'))
@pytest.mark.parametrize('phase_unit', ('rad', 'deg'))
def test_time_offset_angle_at_beam_no_phase_zero_beam_pos_anti_clockwise_single_angle(
    nexus_chopper, beam_position_unit, phase_unit
):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'beam_position': sc.scalar(0.0, unit=beam_position_unit),
            'phase': sc.scalar(0.0, unit=phase_unit),
            'rotation_speed': sc.scalar(2.3, unit='Hz'),
        }
    )
    omega = 2 * pi * 2.3
    sc.testing.assert_identical(
        ch.time_offset_angle_at_beam(angle=sc.scalar(0.0, unit='rad')),
        sc.scalar(1 / 2.3, unit='s'),
    )
    sc.testing.assert_identical(
        ch.time_offset_angle_at_beam(angle=sc.scalar(0.0, unit='deg')),
        sc.scalar(1 / 2.3, unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(1.2, unit='rad')),
        sc.scalar((2 * pi - 1.2) / omega, unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(-0.4, unit='rad')),
        sc.scalar((2 * pi + 0.4) / omega, unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(7.1, unit='rad')),
        sc.scalar((2 * pi - 7.1) / omega, unit='s'),
    )


@pytest.mark.parametrize('beam_position_unit', ('rad', 'deg'))
@pytest.mark.parametrize('phase_unit', ('rad', 'deg'))
def test_time_offset_angle_at_beam_no_phase_zero_beam_pos_clockwise_multi_angle(
    nexus_chopper, beam_position_unit, phase_unit
):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'beam_position': sc.scalar(0.0, unit=beam_position_unit),
            'phase': sc.scalar(0.0, unit=phase_unit),
            'rotation_speed': sc.scalar(-4.4, unit='Hz'),
        }
    )
    omega = 2 * pi * 4.4
    angles = sc.array(dims=['angle'], values=[0.0, 0.4, -1.3, 6.9], unit='rad')
    expected = sc.array(dims=['angle'], values=[0.0, 0.4, -1.3, 6.9], unit='s') / omega
    assert sc.allclose(ch.time_offset_angle_at_beam(angle=angles), expected)


@pytest.mark.parametrize('beam_position_unit', ('rad', 'deg'))
@pytest.mark.parametrize('phase_unit', ('rad', 'deg'))
def test_time_offset_angle_at_beam_no_phase_zero_beam_pos_anti_clockwise_multi_angle(
    nexus_chopper, beam_position_unit, phase_unit
):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'beam_position': sc.scalar(0.0, unit=beam_position_unit),
            'phase': sc.scalar(0.0, unit=phase_unit),
            'rotation_speed': sc.scalar(4.4, unit='Hz'),
        }
    )
    omega = 2 * pi * 4.4
    offset = sc.scalar(2 * pi / omega, unit='s')
    angles = sc.array(dims=['angle'], values=[0.0, 0.4, -1.3, 6.9], unit='rad')
    expected = (
        offset
        - sc.array(dims=['angle'], values=[0.0, 0.4, -1.3, 6.9], unit='s') / omega
    )
    assert sc.allclose(ch.time_offset_angle_at_beam(angle=angles), expected)


@pytest.mark.parametrize('phase_unit', ('rad', 'deg'))
def test_time_offset_angle_at_beam_no_phase_with_beam_pos_clockwise(
    nexus_chopper, phase_unit
):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'beam_position': sc.scalar(1.8, unit='rad'),
            'phase': sc.scalar(0.0, unit=phase_unit),
            'rotation_speed': sc.scalar(-2.3, unit='Hz'),
        }
    )
    omega = 2 * pi * 2.3
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(0.0, unit='rad')),
        sc.scalar(-1.8 / omega, unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(1.8, unit='rad')),
        sc.scalar(0.0, unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(2.4, unit='rad')),
        sc.scalar((2.4 - 1.8) / omega, unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(7.1, unit='rad')),
        sc.scalar((7.1 - 1.8) / omega, unit='s'),
    )


@pytest.mark.parametrize('phase_unit', ('rad', 'deg'))
def test_time_offset_angle_at_beam_no_phase_with_beam_pos_anti_clockwise(
    nexus_chopper, phase_unit
):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'beam_position': sc.scalar(1.8, unit='rad'),
            'phase': sc.scalar(0.0, unit=phase_unit),
            'rotation_speed': sc.scalar(2.3, unit='Hz'),
        }
    )
    omega = 2 * pi * 2.3
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(0.0, unit='rad')),
        sc.scalar((2 * pi + 1.8) / omega, unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(1.8, unit='rad')),
        sc.scalar(1 / 2.3, unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(2.4, unit='rad')),
        sc.scalar((2 * pi - 2.4 + 1.8) / omega, unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(7.1, unit='rad')),
        sc.scalar((2 * pi - 7.1 + 1.8) / omega, unit='s'),
    )


@pytest.mark.parametrize('beam_position_unit', ('rad', 'deg'))
def test_time_offset_angle_at_beam_with_phase_zero_beam_pos_clockwise(
    nexus_chopper, beam_position_unit
):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'beam_position': sc.scalar(0.0, unit=beam_position_unit),
            'phase': sc.scalar(-0.7, unit='rad'),
            'rotation_speed': sc.scalar(-1.1, unit='Hz'),
        }
    )
    omega = 2 * pi * 1.1
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(0.0, unit='rad')),
        sc.scalar(0.7 / omega, unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(1.8, unit='rad')),
        sc.scalar((1.8 + 0.7) / omega, unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(2.4, unit='rad')),
        sc.scalar((2.4 + 0.7) / omega, unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(7.1, unit='rad')),
        sc.scalar((7.1 + 0.7) / omega, unit='s'),
    )


@pytest.mark.parametrize('beam_position_unit', ('rad', 'deg'))
def test_time_offset_angle_at_beam_with_phase_zero_beam_pos_anti_clockwise(
    nexus_chopper, beam_position_unit
):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'beam_position': sc.scalar(0.0, unit=beam_position_unit),
            'phase': sc.scalar(-0.7, unit='rad'),
            'rotation_speed': sc.scalar(1.1, unit='Hz'),
        }
    )
    omega = 2 * pi * 1.1
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(0.0, unit='rad')),
        sc.scalar((2 * pi - 0.7) / omega, unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(1.8, unit='rad')),
        sc.scalar((2 * pi - 1.8 - 0.7) / omega, unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(2.4, unit='rad')),
        sc.scalar((2 * pi - 2.4 - 0.7) / omega, unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_angle_at_beam(angle=sc.scalar(7.1, unit='rad')),
        sc.scalar((2 * pi - 7.1 - 0.7) / omega, unit='s'),
    )


@pytest.mark.parametrize(
    'phase', (sc.scalar(0.0, unit='rad'), sc.scalar(1.2, unit='rad'))
)
def test_time_offset_open_close_no_slit(nexus_chopper, phase):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'phase': sc.scalar(-0.7, unit='rad'),
            'slit_edges': sc.zeros(sizes={'slit': 0, 'edge': 2}, unit='rad'),
        }
    )
    sc.testing.assert_identical(
        ch.time_offset_open(pulse_frequency=ch.rotation_speed),
        sc.zeros(sizes={'slit': 0}, unit='s'),
    )
    sc.testing.assert_identical(
        ch.time_offset_close(pulse_frequency=ch.rotation_speed),
        sc.zeros(sizes={'slit': 0}, unit='s'),
    )
    sc.testing.assert_identical(
        ch.open_duration(pulse_frequency=ch.rotation_speed),
        sc.zeros(sizes={'slit': 0}, unit='s'),
    )


@pytest.mark.parametrize('rotation_speed', (5.12, -3.6))
def test_time_offset_open_close_only_slit(nexus_chopper, rotation_speed):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'beam_position': sc.scalar(0.0, unit='rad'),
            'phase': sc.scalar(0.0, unit='rad'),
            'rotation_speed': sc.scalar(rotation_speed, unit='Hz'),
            'slit_edges': sc.array(
                dims=['slit', 'edge'], values=[[0.0, 360.0]], unit='deg'
            ),
        }
    )
    factor = deg_angle_to_time_factor(rotation_speed)
    assert sc.allclose(
        ch.time_offset_open(pulse_frequency=ch.rotation_speed),
        sc.array(dims=['slit'], values=[factor * 0.0], unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_close(pulse_frequency=ch.rotation_speed),
        sc.array(dims=['slit'], values=[factor * 360.0], unit='s'),
    )
    assert sc.allclose(
        ch.open_duration(pulse_frequency=ch.rotation_speed),
        sc.array(dims=['slit'], values=[1 / abs(rotation_speed)], unit='s'),
    )


@pytest.mark.parametrize(
    'phase',
    (
        sc.scalar(0.0, unit='rad'),
        sc.scalar(1.2, unit='rad'),
        sc.scalar(-50.0, unit='deg'),
    ),
)
@pytest.mark.parametrize(
    'beam_position',
    (
        sc.scalar(0.0, unit='rad'),
        sc.scalar(-0.5, unit='rad'),
        sc.scalar(45.8, unit='deg'),
    ),
)
def test_time_offset_open_close_one_slit_clockwise(nexus_chopper, phase, beam_position):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'beam_position': beam_position,
            'phase': phase,
            'rotation_speed': sc.scalar(-7.21, unit='Hz'),
            'slit_edges': sc.array(
                dims=['slit', 'edge'], values=[[87.0, 177.0]], unit='deg'
            ),
        }
    )
    factor = deg_angle_to_time_factor(-7.21)
    shift = (phase.to(unit='deg') + beam_position.to(unit='deg')).value
    assert sc.allclose(
        ch.time_offset_open(pulse_frequency=ch.rotation_speed),
        sc.array(dims=['slit'], values=[(87.0 - shift) * factor], unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_close(pulse_frequency=ch.rotation_speed),
        sc.array(dims=['slit'], values=[(177.0 - shift) * factor], unit='s'),
    )
    assert sc.allclose(
        ch.open_duration(pulse_frequency=ch.rotation_speed),
        sc.array(dims=['slit'], values=[90.0 * factor], unit='s'),
    )


@pytest.mark.parametrize(
    'phase',
    (
        sc.scalar(0.0, unit='rad'),
        sc.scalar(1.2, unit='rad'),
        sc.scalar(-50.0, unit='deg'),
    ),
)
@pytest.mark.parametrize(
    'beam_position',
    (
        sc.scalar(0.0, unit='rad'),
        sc.scalar(-0.5, unit='rad'),
        sc.scalar(45.8, unit='deg'),
    ),
)
def test_time_offset_open_close_one_slit_anticlockwise(
    nexus_chopper, phase, beam_position
):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'beam_position': beam_position,
            'phase': phase,
            'rotation_speed': sc.scalar(7.21, unit='Hz'),
            'slit_edges': sc.array(
                dims=['slit', 'edge'], values=[[87.0, 177.0]], unit='deg'
            ),
        }
    )
    factor = deg_angle_to_time_factor(7.21)
    shift = (phase.to(unit='deg') + beam_position.to(unit='deg')).value
    assert sc.allclose(
        ch.time_offset_open(pulse_frequency=ch.rotation_speed),
        sc.array(dims=['slit'], values=[(360 - 177.0 + shift) * factor], unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_close(pulse_frequency=ch.rotation_speed),
        sc.array(dims=['slit'], values=[(360 - 87.0 + shift) * factor], unit='s'),
    )
    assert sc.allclose(
        ch.open_duration(pulse_frequency=ch.rotation_speed),
        sc.array(dims=['slit'], values=[90.0 * factor], unit='s'),
    )


@pytest.mark.parametrize(
    'phase',
    (
        sc.scalar(0.0, unit='rad'),
        sc.scalar(1.2, unit='rad'),
        sc.scalar(-50.0, unit='deg'),
    ),
)
@pytest.mark.parametrize(
    'beam_position',
    (
        sc.scalar(0.0, unit='rad'),
        sc.scalar(-0.5, unit='rad'),
        sc.scalar(45.8, unit='deg'),
    ),
)
def test_time_offset_open_close_one_slit_across_tdc_clockwise(
    nexus_chopper, phase, beam_position
):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'beam_position': beam_position,
            'phase': phase,
            'rotation_speed': sc.scalar(-7.21, unit='Hz'),
            'slit_edges': sc.array(
                dims=['slit', 'edge'], values=[[330.0, 380.0]], unit='deg'
            ),
        }
    )
    factor = deg_angle_to_time_factor(-7.21)
    shift = (phase.to(unit='deg') + beam_position.to(unit='deg')).value
    assert sc.allclose(
        ch.time_offset_open(pulse_frequency=ch.rotation_speed),
        sc.array(dims=['slit'], values=[(330.0 - shift) * factor], unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_close(pulse_frequency=ch.rotation_speed),
        sc.array(dims=['slit'], values=[(380.0 - shift) * factor], unit='s'),
    )
    assert sc.allclose(
        ch.open_duration(pulse_frequency=ch.rotation_speed),
        sc.array(dims=['slit'], values=[50.0 * factor], unit='s'),
    )


@pytest.mark.parametrize(
    'phase',
    (
        sc.scalar(0.0, unit='rad'),
        sc.scalar(1.2, unit='rad'),
        sc.scalar(-50.0, unit='deg'),
    ),
)
@pytest.mark.parametrize(
    'beam_position',
    (
        sc.scalar(0.0, unit='rad'),
        sc.scalar(-0.5, unit='rad'),
        sc.scalar(45.8, unit='deg'),
    ),
)
def test_time_offset_open_close_one_slit_across_tdc_anticlockwise(
    nexus_chopper, phase, beam_position
):
    ch = DiskChopper.from_nexus(
        {
            **nexus_chopper,
            'beam_position': beam_position,
            'phase': phase,
            'rotation_speed': sc.scalar(7.21, unit='Hz'),
            'slit_edges': sc.array(
                dims=['slit', 'edge'], values=[[330.0, 380.0]], unit='deg'
            ),
        }
    )
    factor = deg_angle_to_time_factor(7.21)
    shift = (phase.to(unit='deg') + beam_position.to(unit='deg')).value
    assert sc.allclose(
        ch.time_offset_open(pulse_frequency=ch.rotation_speed),
        sc.array(dims=['slit'], values=[(360 - 380.0 + shift) * factor], unit='s'),
    )
    assert sc.allclose(
        ch.time_offset_close(pulse_frequency=ch.rotation_speed),
        sc.array(dims=['slit'], values=[(360 - 330.0 + shift) * factor], unit='s'),
    )
    assert sc.allclose(
        ch.open_duration(pulse_frequency=ch.rotation_speed),
        sc.array(dims=['slit'], values=[50.0 * factor], unit='s'),
    )


def test_time_offset_open_close_source_frequency_not_multiple_of_chopper(nexus_chopper):
    ch = DiskChopper.from_nexus(
        {**nexus_chopper, 'rotation_speed': sc.scalar(4.52, unit='Hz')}
    )
    with pytest.raises(ValueError):
        ch.time_offset_open(pulse_frequency=sc.scalar(4.3, unit='Hz'))
    with pytest.raises(ValueError):
        ch.time_offset_close(pulse_frequency=sc.scalar(5.1, unit='Hz'))


def test_disk_chopper_svg(nexus_chopper):
    ch = DiskChopper.from_nexus(nexus_chopper)
    assert ch.make_svg()


def test_disk_chopper_svg_custom_dim_names(nexus_chopper):
    nexus_chopper['slit_edges'] = nexus_chopper['slit_edges'].rename_dims(slit='dim_0')
    ch = DiskChopper.from_nexus(nexus_chopper)
    assert ch.make_svg()
