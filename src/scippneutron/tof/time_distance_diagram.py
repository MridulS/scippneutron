import scipp as sc
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


def deg_to_rad(x):
    return x * np.pi / 180.0


class Chopper:
    def __init__(self,
                 frequency=0,
                 openings=None,
                 distance=0,
                 phase=0,
                 unit="rad",
                 name=""):
        # openings is list. First entry is start angle of the first cut-out
        # second entry is end angle of first cut-out, etc.
        self.frequency = frequency
        self.openings = openings
        self.omega = 2.0 * np.pi * frequency
        self.distance = distance
        self.phase = phase
        if unit == "deg":
            self.openings = deg_to_rad(self.openings)
            self.phase = deg_to_rad(self.phase)
        self.name = name


class Beamline:
    def __init__(self,
                 ax,
                 *,
                 tmax,
                 Lmax,
                 frame_rate=14.0 * sc.Unit('Hz'),
                 frame_offset=0.0 * sc.Unit('ms')):
        self._ax = ax
        self._time_unit = sc.Unit('ms')
        self._frame_length = (1.0 / frame_rate).to(unit=self._time_unit)
        self._tmax = tmax.to(unit=self._time_unit)
        self._Lmax = Lmax.to(unit='m')
        self._frame_offset = frame_offset.to(unit=self._time_unit)
        self._ax.set_xlabel(f"Time [{self._time_unit}]")
        self._ax.set_ylabel("Distance [m]")

    def add_annotations(self):
        x0 = self._frame_length
        x1 = self._frame_length + self._frame_offset
        self._ax.annotate('',
                          xy=(x0.value, 0),
                          xytext=(x1.value, 0),
                          arrowprops=dict(arrowstyle='<|-|>'))
        self._ax.text((x1 + x0).value / 2, 0.1, r'$\Delta T_0$')

    def add_source_pulse(self, pulse_length=3.0 * sc.Unit('ms')):
        self._pulse_length = pulse_length.to(unit=self._time_unit)
        # Define and draw source pulse
        x0 = self._frame_offset.value
        x1 = self._pulse_length.value
        y0 = 0.0
        psize = 1.0
        rect = Rectangle((x0, y0),
                         x1,
                         -psize,
                         lw=1,
                         fc='orange',
                         ec='k',
                         hatch="////",
                         zorder=10)
        self._ax.add_patch(rect)
        x0 += self._frame_length.value
        rect = Rectangle((x0, y0),
                         x1,
                         -psize,
                         lw=1,
                         fc='orange',
                         ec='k',
                         hatch="////",
                         zorder=10)
        self._ax.add_patch(rect)
        self._ax.text(x0,
                      -psize,
                      f"Source pulse ({pulse_length.value} {pulse_length.unit})",
                      ha="left",
                      va="top",
                      fontsize=6)

    def add_event_time_zero(self):
        ls = 'dotted'
        x = 0
        while x < self._tmax.value:
            self._ax.axvline(x=x, ls=ls)
            x += self._frame_length.value

    def add_neutron_pulse(self, tof_min=150.0 * sc.Unit('ms')):
        x0 = self._frame_offset
        x1 = x0 + self._pulse_length
        x3 = x1 + tof_min + 0.95 * self._frame_length  # small gap
        x4 = x0 + tof_min
        y0 = 0
        y1 = self._Lmax.value
        x = sc.concat([x0, x1, x3, x4], 'x')
        self._ax.fill(x.values, [y0, y0, y1, y1], alpha=0.3)
        x += self._frame_length
        self._ax.fill(x.values, [y0, y0, y1, y1], alpha=0.3)

    def add_detector(self, *, distance, name='detector'):
        self._ax.plot([0, self._tmax.max().value], [distance.value, distance.value],
                      lw=3,
                      color='grey')
        self._ax.text(0.0, distance.value, name, va="bottom", ha="left")


def time_distance_diagram(tmax=300 * sc.Unit('ms')):
    fig, ax = plt.subplots(1, 1)
    beamline = Beamline(ax,
                        tmax=tmax,
                        Lmax=40.0 * sc.Unit('m'),
                        frame_offset=17.8 * sc.Unit('ms'))
    beamline.add_event_time_zero()
    beamline.add_source_pulse()
    beamline.add_detector(distance=30.0 * sc.Unit('m'), name='detector1')
    beamline.add_detector(distance=40.0 * sc.Unit('m'), name='detector2')
    beamline.add_neutron_pulse()
    beamline.add_annotations()

    return fig
