# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2022 Scipp contributors (https://github.com/scipp)
# @author Jan-Lukas Wynen

from typing import Callable, Dict, Tuple, Union

import scipp as sc

from ..conversion import beamline, tof


_NO_SCATTER_GRAPH_KINEMATICS = {
    'Ltotal': beamline.total_straight_beam_length_no_scatter,
}

_NO_SCATTER_GRAPH = {
    **_NO_SCATTER_GRAPH_KINEMATICS,
    'wavelength': tof.wavelength_from_tof,
    'energy': tof.energy_from_tof,
}

_SCATTER_GRAPH_KINEMATICS = {
    'incident_beam': beamline.straight_incident_beam,
    'scattered_beam': beamline.straight_scattered_beam,
    'L1': beamline.L1,
    'L2': beamline.L2,
    'two_theta': beamline.two_theta,
    'Ltotal': beamline.total_beam_length,
}

_SCATTER_GRAPH_DYNAMICS_BY_ORIGIN = {
    'energy': {
        'dspacing': tof.dspacing_from_energy,
        'wavelength': tof.wavelength_from_energy,
    },
    'tof': {
        'dspacing': tof.dspacing_from_tof,
        'energy': tof.energy_from_tof,
        'Q': tof.Q_from_wavelength,
        'wavelength': tof.wavelength_from_tof,
    },
    'Q': {
        'wavelength': tof.wavelength_from_Q,
    },
    'wavelength': {
        'dspacing': tof.dspacing_from_wavelength,
        'energy': tof.energy_from_wavelength,
        'Q': tof.Q_from_wavelength,
    },
}


def _inelastic_scatter_graph(energy_mode):
    inelastic_step = {
        'direct_inelastic': {
            'energy_transfer': tof.energy_transfer_direct_from_tof
        },
        'indirect_inelastic': {
            'energy_transfer': tof.energy_transfer_indirect_from_tof
        }
    }[energy_mode]
    return {**_SCATTER_GRAPH_KINEMATICS, **inelastic_step}


def _reachable_by(target, graph):
    return any(target == targets if isinstance(targets, str) else target in targets
               for targets in graph.keys())


def _elastic_scatter_graph(origin, target):
    if _reachable_by(target, _SCATTER_GRAPH_KINEMATICS):
        return dict(_SCATTER_GRAPH_KINEMATICS)
    return {**_SCATTER_GRAPH_KINEMATICS, **_SCATTER_GRAPH_DYNAMICS_BY_ORIGIN[origin]}


def _scatter_graph(origin, target, energy_mode):
    graph = (_elastic_scatter_graph(origin, target)
             if energy_mode == 'elastic' else _inelastic_scatter_graph(energy_mode))
    return graph


def conversion_graph(origin: str, target: str, scatter: bool,
                     energy_mode: str) -> Dict[Union[str, Tuple[str]], Callable]:
    """
    Get a conversion graph for given parameters.

    The graph can be used with `scipp.transform_coords`.

    :param origin: Name of the input coordinate.
    :param target: Name of the output coordinate.
    :param scatter: Choose whether to use scattering or non-scattering conversions.
    :param energy_mode: Select if energy is conserved. One of `'elastic'`,
                        `'direct_inelastic'`, `'indirect_inelastic'`.
    :return: Conversion graph.
    :seealso: :py:func:`scippneutron.convert`,
              :py:func:`scippneutron.deduce_conversion_graph`.
    """

    # Results are copied to ensure users do not modify the global dictionaries.
    if scatter:
        return dict(_scatter_graph(origin, target, energy_mode))
    else:
        return dict(_NO_SCATTER_GRAPH)


def _find_inelastic_inputs(data):
    return [name for name in ('incident_energy', 'final_energy') if name in data.coords]


def _deduce_energy_mode(data, origin, target):
    inelastic_inputs = _find_inelastic_inputs(data)
    if target == 'energy_transfer':
        if len(inelastic_inputs) > 1:
            raise RuntimeError(
                "Data contains coords for incident *and* final energy, cannot have "
                "both for inelastic scattering.")
        if len(inelastic_inputs) == 0:
            raise RuntimeError(
                "Data contains neither coords for incident nor for final energy, this "
                "does not appear to be inelastic-scattering data, cannot convert to "
                "energy transfer.")
        return {
            'incident_energy': 'direct_inelastic',
            'final_energy': 'indirect_inelastic'
        }[inelastic_inputs[0]]

    if 'energy' in (origin, target):
        if inelastic_inputs:
            raise RuntimeError(
                f"Data contains coords for inelastic scattering "
                f"({inelastic_inputs}) but conversion with elastic energy requested. "
                f"This is not implemented.")
    return 'elastic'


def deduce_conversion_graph(data: Union[sc.DataArray,
                                        sc.Dataset], origin: str, target: str,
                            scatter: bool) -> Dict[Union[str, Tuple[str]], Callable]:
    """
    Get the conversion graph used by :py:func:`scippneutron.convert`
    when called with identical arguments.

    :param data: Input data.
    :param origin: Name of the input coordinate.
    :param target: Name of the output coordinate.
    :param scatter: Choose whether to use scattering or non-scattering conversions.
    :return: Conversion graph.
    :seealso: :py:func:`scippneutron.convert`, :py:func:`scippneutron.conversion_graph`.
    """
    return conversion_graph(origin, target, scatter,
                            _deduce_energy_mode(data, origin, target))


def convert(data: Union[sc.DataArray, sc.Dataset], origin: str, target: str,
            scatter: bool) -> Union[sc.DataArray, sc.Dataset]:
    """
    Perform a unit conversion from the given origin unit to target.
    See the the documentation page on "Coordinate Transformations"
    (https://scipp.github.io/scippneutron/user-guide/coordinate-transformations.html)
    for more details.

    :param data: Input data.
    :param origin: Name of the input coordinate.
    :param target: Name of the output coordinate.
    :param scatter: Choose whether to use scattering or non-scattering conversions.
    :return: A new scipp.DataArray or scipp.Dataset with the new coordinate.
    :seealso: :py:func:`scippneutron.deduce_conversion_graph` and
              :py:func:`scippneutron.conversion_graph` to inspect
              the possible conversions.
    """

    graph = deduce_conversion_graph(data, origin, target, scatter)

    try:
        converted = data.transform_coords(target, graph=graph)
    except KeyError as err:
        if err.args[0] == target:
            raise RuntimeError(f"No viable conversion from '{origin}' to '{target}' "
                               f"with scatter={scatter}.")
        raise RuntimeError(f"Missing coordinate '{err.args[0]}' for conversion "
                           f"from '{origin}' to '{target}'") from None

    return converted
