# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2023 Scipp contributors (https://github.com/scipp)

r"""Tools for disk choppers.

Definitions
-----------

The names used here correspond closely to the names used by NeXus' ``NXdisk_chopper``.
See https://manual.nexusformat.org/classes/base_classes/NXdisk_chopper.html
for an overview.

Here is how those attributes are interpreted in ScippNeutron:
The image below shows a disk chopper with a single slit
as seen from the neutron source looking towards the sample.
Note that all definitions are independent of the rotation direction.

.. list-table::
    :widths: auto
    :header-rows: 1

    * - Name
      - Symbol
      - Definition
    * - ``top_dead_center``
      - :math:`t_0`
      - Choppers typically have a top-dead-center (TDC) sensor that tracks the
        rotation of the chopper.
        The sensor emits a timestamp when a chosen part of the chopper disk passes by.
        This part of the disk serves as a reference point for defining angles;
        it is marked as 'TDC' in the image below.

        The emitted timestamps are stored in the ``top_dead_center`` field
        of a NeXus chopper.
        This serves as a reference time for the chopper :math:`t_0`.
        In :class:`DiskChopper`, the TDC is encoded as a component of
        :attr:`DiskChopper.phase`.
    * - ``beam_position``
      - :math:`\tilde{\theta}`
      - The angle under which the beam hits the chopper
        (:attr:`DiskChopper.beam_position`).
        We do not care about the radial position and assume that the beam can
        pass through all chopper slits.
    * - ``slit_edges``
      -
      - Slits are defined in terms of *begin* (:attr:`DiskChopper.slit_begin`,
        :math:`\theta` in the image) and *end* (:attr:`DiskChopper.slit_end`) angles
        that are stored together as :attr:`DiskChopper.slit_edges`.
        See also :func:`scippneutron.chopper.nexus_chopper.post_process_disk_chopper`
        for how to convert from NeXus encoding.
    * - ``rotation_speed``
      - :math:`f`
      - The rotation frequency of the chopper.
        Stored in :attr:`DiskChopper.rotation_speed`.
        A positive frequency means anticlockwise rotation and a negative frequency
        clockwise rotation (as seen from the source).
    * - ``angular_frequency``
      - :math:`\omega`
      - :math:`\omega = 2 \pi f`, :attr:`DiskChopper.angular_frequency`.
    * - ``delay``
      - :math:`\delta t`
      - Delay of the chopper timing system relative to global facility time with
        :math:`t_g = t + \delta t`, where :math:`t_g` is a global time and :math:`t`
        a chopper time.
    * - ``phase``
      - :math:`\phi`
      - The phase of the chopper relative to the pulse time.
        Defined as :math:`\phi = \omega (t_0 + \delta t - T_0)`, see below for
        the explanation.
        (:attr:`DiskChopper.phase`).
    * - ``pulse_time``
      - :math:`T_0`
      - Timestamp of a neutron pulse in global facility time.

.. image:: /_static/chopper/chopper-coordinates.svg
   :width: 400
   :align: center

:class:`DiskChopper` expects the chopper to be in phase with the source.
It thus requires a constant rotation speed which must be an integer
multiple of the source frequency or vice versa.
The phase should be computed as defined about from the difference of a pulse time
and a corresponding TDC timestamp.
The user is responsible for determining the correct times.

Slit openings
-------------

The terminology here differentiates slit 'begin' and 'end' from 'open' and 'close'.
The former refer to the angles relative to TDC as shown in the image above.
The latter refer to the times when a slit opens and closes for the beam.

It is possible to have ``end > 360 deg`` if a slit spans TDC.

For a given slit, we require ``begin < end``.
To also have ``open < close`` for both directions of rotation,
we have the following correspondence:

- clockwise rotation: ``begin`` <-> ``open`` and ``end`` <-> ``close``
- anticlockwise rotation: ``begin`` <-> ``close`` and ``end`` <-> ``open``

Time calculations
-----------------

Given the definitions above, the time in the global timing system when a point
at angle :math:`\theta` is at the beam position is

.. math::

    t_g(\theta) &= t_0 + \delta t + \begin{cases}
    \frac{\theta-\tilde{\theta}}{|\omega|}, & \textsf{clockwise}\\
    \frac{2\pi - (\theta-\tilde{\theta})}{|\omega|}, & \textsf{anticlockwise}
    \end{cases}\\
    &= t_0 + \delta t + - \frac{\theta - \tilde{\theta}}{\omega} + \begin{cases}
    0, & \textsf{clockwise}\\
    \frac{2\pi}{\omega}, & \textsf{anticlockwise}
    \end{cases}

where the second line uses that, for clockwise rotation, :math:`|\omega| = -\omega`
and for anticlockwise, :math:`|\omega| = \omega`.
This can be converted to a time offset from a pulse time :math:`T_0` using

.. math::

    \Delta t_g(\theta) = t_g(\theta) - T_0 = - \frac{\theta - \tilde{\theta}
       - \phi}{\omega}
       + \begin{cases}
         0, & \textsf{clockwise}\\
         \frac{2\pi}{\omega}, & \textsf{anticlockwise}
         \end{cases}

where :math:`\phi = \omega (t_0 + \delta t - T_0)` is the ``phase``.

:meth:`DiskChopper.time_offset_angle_at_beam` can calculate :math:`\Delta t_g(\theta)`
and :meth:`DiskChopper.time_offset_open` :meth:`DiskChopper.time_offset_close` calculate
:math:`\Delta t_g` for slit open and close times.

The definitions used here can lead to surprising results, especially when
:math:`\tilde{\theta} \neq 0` or :math:`\phi \neq 0`.
The plots below show the computed times for an angle :math:`\theta` for
:math:`\tilde{\theta} \neq 0` and :math:`\phi = 0` (blue lines).
Note in particular the time ranges for :math:`\theta \in [0, 2\pi)` (gray rectangles).
The other lines show :math:`\Delta t_g \,\mathsf{mod}\, 1/f` which is an option
for restricting the times onto :math:`[0, \frac{2\pi}{|\omega|}) = [0, \frac1{f})`.

.. image:: /_static/chopper/disk-chopper-time-curve.svg
   :class: only-light
   :width: 700
   :align: center

.. image:: /_static/chopper/disk-chopper-time-curve-dark.svg
   :class: only-dark
   :width: 700
   :align: center

|

:meth:`DiskChopper.time_offset_open` and :meth:`DiskChopper.time_offset_close`
compute :math:`\Delta t_g` for the slit edges.
The resulting times are shown below for a chopper with two slits, a short one (blue)
and a long one (orange/yellow) with
:math:`\theta_\mathsf{short} < \theta_\mathsf{long}`.
Source pulses are indicated in gray.
The shown frequency ratio is ``rotation_speed / pulse_frequency``.

Times were computed for a pulse at :math:`T_0` with length :math:`\Delta T` but spill
into neighboring pulses because of a nonzero beam position and phase.
If those were zero, the :math:`\mathsf{frequency\ ratio} \geq 1` openings would lie
within :math:`[T_0,\, T_0 + \Delta T)` and the :math:`\mathsf{frequency\ ratio} = 0.5`
openings would lie within :math:`[T_0,\, T_0 + 2\Delta T)`.
Note how, for choppers that spin at a multiple of the pulse frequency, there are
multiple openings per slit.

.. image:: /_static/chopper/disk-chopper-openings.svg
   :class: only-light
   :width: 700
   :align: center

.. image:: /_static/chopper/disk-chopper-openings-dark.svg
   :class: only-dark
   :width: 700
   :align: center
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any, Optional, Union
from uuid import uuid4

import numpy as np
import scipp as sc
import scipp.constants

try:
    # Python 3.11+
    from enum import StrEnum

    class DiskChopperType(StrEnum):
        """Type of disk chopper."""

        single = 'Chopper type single'
        contra_rotating_pair = 'contra_rotating_pair'
        synchro_pair = 'synchro_pair'

    del StrEnum

except ImportError:
    from enum import Enum

    class DiskChopperType(str, Enum):  # type: ignore[no-redef]
        """Type of disk chopper."""

        single = 'Chopper type single'
        contra_rotating_pair = 'contra_rotating_pair'
        synchro_pair = 'synchro_pair'

    del Enum


@dataclasses.dataclass(frozen=True, eq=False)
class DiskChopper:
    """A disk chopper.

    Encode parameters of a single disk chopper and provides methods for computing
    slit opening times.
    This class requires that the chopper be in phase with the neutron source and that
    the rotation frequency be constant.

    See Also
    --------
    scippneutron.chopper.disk_chopper:
        For detailed documentation of the definitions and calculations used
        by ``DiskChopper``.
    """

    position: sc.Variable
    """Position of the chopper.

    This is the center point of the chopper's axle in the face towards the source.
    See https://manual.nexusformat.org/classes/base_classes/NXdisk_chopper.html
    """
    rotation_speed: sc.Variable
    """Rotation frequency of the chopper."""
    beam_position: sc.Variable
    """Angle where the beam crosses the chopper."""
    phase: sc.Variable
    r"""Phase of the chopper rotation relative to the source pulses.

    Defined as :math:`\phi = \omega (t_0 + \delta t - T_0)`, where :math:`t_0` is a
    TDC timestamp, :math:`\delta t` is the chopper delay, and  :math:`T_0`
    is the pulse time.
    """
    slit_edges: sc.Variable
    """Edges of the slits as angles measured anticlockwise from top-dead-center.

    A 2d array of the form ``[[begin_0, end_0], [begin_1, end_1], ...]``.
    The order of slits is arbitrary.
    """
    slit_height: Optional[sc.Variable] = None
    """Distance from chopper outer edge to bottom of slits."""
    radius: Optional[sc.Variable] = None
    """Radius of the chopper."""

    def __post_init__(self) -> None:
        # Check for frequency because not all NeXus files store a unit
        # and the name can be confusing.
        _require_frequency('rotation_speed', self.rotation_speed)

    @classmethod
    def from_nexus(
        cls, dg: Mapping[str, Optional[sc.Variable, sc.DataArray]]
    ) -> DiskChopper:
        if (typ := dg.get('type', DiskChopperType.single)) != DiskChopperType.single:
            raise NotImplementedError(
                'Class DiskChopper only supports single choppers,'
                f'got chopper type {typ}'
            )
        return DiskChopper(
            position=dg['position'],
            rotation_speed=_get_1d_variable(dg, 'rotation_speed'),
            beam_position=_get_1d_variable(dg, 'beam_position'),
            phase=_get_1d_variable(dg, 'phase'),
            slit_edges=dg['slit_edges'],
            slit_height=dg.get('slit_height'),
            radius=dg.get('radius'),
        )

    @property
    def slit_begin(self) -> sc.Variable:
        """Beginning edges of the slits."""
        return self.slit_edges[self.slit_edges.dims[1], 0]

    @property
    def slit_end(self) -> sc.Variable:
        """Ending edges of the slits."""
        return self.slit_edges[self.slit_edges.dims[1], 1]

    @property
    def n_slits(self) -> int:
        """Number of slits."""
        return self.slit_edges.shape[0]

    @property
    def angular_frequency(self) -> sc.Variable:
        """Rotation speed as an angular frequency in ``rad * rotation_speed.unit``."""
        return sc.scalar(2.0, unit="rad") * sc.constants.pi * self.rotation_speed

    @property
    def is_clockwise(self) -> bool:
        """Return True if the chopper rotates clockwise."""
        return (self.rotation_speed < 0.0 * self.rotation_speed.unit).value

    def time_offset_open(self, *, pulse_frequency: sc.Variable) -> sc.Variable:
        r"""Return the opening time offsets of the chopper slits.

        Computes :math:`\Delta t_g(\theta)` as defined in
        :mod:`scippneutron.chopper.disk_chopper` with :math:`\theta` = ``slit_begin``
        for clockwise rotation and :math:`\theta` = ``slit_end`` otherwise.

        If the chopper spins at a multiple of the pulse frequency, each slit shows up
        multiple times in the result such that the array covers an entire pulse
        length.
        If the chopper spins slower than the pulse frequency, only one time per slit
        is returned, but the result covers more than one pulse in time.
        See the module documentation :mod:`scippneutron.chopper.disk_chopper`
        for details.

        Parameters
        ----------
        pulse_frequency;
            Frequency of the neutron source.

        Returns
        -------
        :
            Variable of opening times as offsets from the pulse time.
        """
        slit_edges = self.slit_begin if self.is_clockwise else self.slit_end
        return self.time_offset_angle_at_beam(
            angle=slit_edges, n_repetitions=self._source_phase_factor(pulse_frequency)
        )

    def time_offset_close(self, *, pulse_frequency: sc.Variable) -> sc.Variable:
        r"""Return the opening time offsets of the chopper slits.

        Computes :math:`\Delta t_g(\theta)` as defined in
        :mod:`scippneutron.chopper.disk_chopper` with :math:`\theta` = ``slit_end``
        for clockwise rotation and :math:`\theta` = ``slit_start`` otherwise.

        If the chopper spins at a multiple of the pulse frequency, each slit shows up
        multiple times in the result such that the array covers an entire pulse
        length.
        If the chopper spins slower than the pulse frequency, only one time per slit
        is returned, but the result covers more than one pulse in time.
        See the module documentation :mod:`scippneutron.chopper.disk_chopper`
        for details.

        Parameters
        ----------
        pulse_frequency;
            Frequency of the neutron source.

        Returns
        -------
        :
            Variable of opening times as offsets from the pulse time.
        """
        slit_edges = self.slit_end if self.is_clockwise else self.slit_begin
        return self.time_offset_angle_at_beam(
            angle=slit_edges, n_repetitions=self._source_phase_factor(pulse_frequency)
        )

    def time_offset_angle_at_beam(
        self, *, angle: sc.Variable, n_repetitions: int = 1
    ) -> sc.Variable:
        r"""Return the time offset when an angle on the chopper is at the beam.

        The time is an offset from the given pulse time.
        It encodes the time when the given angle passes by the beam position.

        Computes :math:`\Delta t_g(\theta)` as defined in
        :mod:`scippneutron.chopper.disk_chopper`.

        Parameters
        ----------
        angle:
            Angle to compute time for.
            Defined anticlockwise with respect to top-dead-center.
        n_repetitions:
            Return this many times for each angle corresponding to multiple rotations
            of the chopper.

        Returns
        -------
        :
            Computed time offset.
        """
        angle = self._apply_angle_repetitions(angle=angle, n_repetitions=n_repetitions)
        angle = (
            self.beam_position.to(unit='rad')
            + self.phase.to(unit='rad')
            - angle.to(unit='rad', copy=False)
        )
        if not self.is_clockwise:
            angle = sc.scalar(2.0, unit='rad') * sc.constants.pi + angle
        return angle / self.angular_frequency

    def open_duration(self, *, pulse_frequency: sc.Variable) -> sc.Variable:
        """Return how long the chopper is open for.

        Parameters
        ----------
        pulse_frequency;
            Frequency of the neutron source.

        Returns
        -------
        :
            Variable of opening durations.
        """
        return self.time_offset_close(
            pulse_frequency=pulse_frequency
        ) - self.time_offset_open(pulse_frequency=pulse_frequency)

    def __eq__(self, other: Any) -> Union[bool, NotImplemented]:
        if not isinstance(other, DiskChopper):
            return NotImplemented
        return all(
            _field_eq(getattr(self, field.name), getattr(other, field.name))
            for field in dataclasses.fields(self)
        )

    def make_svg(self, image_size: int = 400) -> str:
        """Generate an SVG image for this chopper.

        Parameters
        ----------
        image_size:
            The size in pixels of the image.

        Returns
        -------
        :
            The SVG image as a string.
        """
        from ._svg import draw_disk_chopper

        return draw_disk_chopper(self, image_size=image_size)

    def _repr_svg_(self) -> str:
        return self.make_svg()

    def _repr_html_(self) -> str:
        from .._html_repr import disk_chopper_html_repr

        return disk_chopper_html_repr(self)

    def _apply_angle_repetitions(
        self, *, angle: sc.Variable, n_repetitions: int
    ) -> sc.Variable:
        dim = str(uuid4())
        if n_repetitions == 1:
            repetition_offsets = sc.scalar(0, unit=angle.unit)
        else:
            # -1 in the end value to exclude the end value from the array.
            repetition_offsets = sc.arange(
                dim, 0.0, n_repetitions * 2 * np.pi - 1, 2 * np.pi, unit='rad'
            )
        if self.is_clockwise:
            repeated = angle + repetition_offsets.to(unit=angle.unit)
        else:
            # Make sure the repeated angles are later in time.
            repeated = angle - repetition_offsets.to(unit=angle.unit)

        if n_repetitions == 1:
            # Do not add a new dimension to the output.
            return repeated
        if angle.ndim == 0:
            return repeated.flatten(to='slit')
        # Remove aux dimension.
        return repeated.transpose([*angle.dims[:-1], dim, angle.dims[-1]]).flatten(
            dims=[dim, angle.dims[-1]], to=angle.dims[-1]
        )

    def _source_phase_factor(self, pulse_frequency: sc.Variable) -> int:
        if self.rotation_speed.ndim != 0:
            raise sc.DimensionError(
                'The chopper rotation speed must be a scalar, '
                f'got dims {self.rotation_speed.sizes}.'
            )
        if pulse_frequency.ndim != 0:
            raise sc.DimensionError(
                'The pulse frequency must be a scalar, '
                f'got dims {pulse_frequency.sizes}.'
            )
        if pulse_frequency.value <= 0:
            raise ValueError(
                f'The pulse frequency must be > 0, got {pulse_frequency:c}.'
            )

        rotation_speed = abs(self.rotation_speed)
        pulse_frequency = pulse_frequency.to(unit=rotation_speed.unit)
        quot = rotation_speed / pulse_frequency
        if not _is_int_or_inverse_int(quot, rtol=sc.scalar(1e-8)):
            raise ValueError(
                'The chopper is out of phase with the source. '
                'The rotation speed must be an integer multiple of the '
                'pulse frequency or vice versa.\n'
                f'pulse_frequency:\n  {pulse_frequency}\n'
                f'rotation_speed:\n  {self.rotation_speed}'
            )
        # If pulse_frequency > rotation_speed, quot < 0 but we want 1 repetition
        # of the slits, so use `max` here:
        return round(max(quot.value, 1))


def _field_eq(a: Any, b: Any) -> bool:
    if isinstance(a, (sc.Variable, sc.DataArray)):
        try:
            return sc.identical(a, b)
        except TypeError:
            return False  # if identical does not support b
    return a == b


def _require_frequency(name: str, x: sc.Variable) -> None:
    try:
        sc.scalar(0.0, unit=x.unit).to(unit='Hz')
    except sc.UnitError:
        raise sc.UnitError(f"'{name}' must be a frequency, got unit {x.unit}") from None


def _len_or_1(x: sc.Variable) -> int:
    if x.ndim == 0:
        return 1
    return len(x)


def _get_1d_variable(
    dg: Mapping[str, Optional[sc.Variable, sc.DataArray]], name: str
) -> sc.Variable:
    if (val := dg.get(name)) is None:
        raise ValueError(f"Chopper field '{name}' is missing")

    msg = (
        "Chopper field '{name}' must be a scalar variable, {got}. " "Use "
    )  # TODO insert use

    if not isinstance(val, sc.Variable):
        raise TypeError(msg.format(name=name, got=f'got a {type(val)}'))
    if val.ndim != 0:
        raise sc.DimensionError(
            msg.format(name=name, got=f'got a {val.ndim}d variable')
        )
    return val


def _is_int_or_inverse_int(x: sc.Variable, *, rtol: sc.Variable) -> bool:
    a = sc.all(abs(sc.round(x) - x) < rtol)
    y = sc.reciprocal(x)
    b = sc.all(abs(sc.round(y) - y) < rtol)
    return bool(a | b)
