# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2023 Scipp contributors (https://github.com/scipp)
"""Models for peaks and background."""

import abc
import math
from typing import Iterable

import numpy as np
import scipp as sc


class Model(abc.ABC):
    def __init__(self, *, prefix: str, param_names: Iterable[str]) -> None:
        """Initialize a base model.

        Parameters
        ----------
        prefix:
            Prefix used for model parameters in all user-facing data.
        param_names:
            Names of parameters in arbitrary order.
            Does not include the prefix.
        """
        self._prefix = prefix
        self._param_names = set(param_names)

    @abc.abstractmethod
    def _call(self, x: sc.Variable, params: dict[str, sc.Variable]) -> sc.Variable:
        """Evaluate the model at given independent variables and parameters.

        The parameters are given *without* the prefix.
        """
        ...

    @abc.abstractmethod
    def _guess(self, x: sc.Variable, y: sc.Variable) -> dict[str, sc.Variable]:
        """Roughly estimate the model parameters.

        Parameters
        ----------
        x:
            Independent variable.
        y:
            Dependent variable.

        Returns
        -------
        :
            Estimated parameters.
            Dict keys are parameter names *without* the prefix.
        """
        ...

    @property
    def prefix(self) -> str:
        return self._prefix

    @property
    def param_names(self) -> set[str]:
        """Parameter names including the prefix."""
        return {self._prefix + name for name in self._param_names}

    def __call__(self, x: sc.Variable, **params: sc.Variable) -> sc.Variable:
        if params.keys() != self.param_names:
            raise ValueError(
                f'Bad parameters for model {self.__class__.__name__},'
                f'got: {set(params.keys())}, expected {self._param_names}'
            )
        return self._call(
            x, {name[len(self._prefix) :]: val for name, val in params.items()}
        )

    def guess(
        self, data: sc.DataArray, *, coord: str | None = None
    ) -> dict[str, sc.Variable]:
        if coord is None:
            coord = data.dim
        return {
            self._prefix + name: param
            for name, param in self._guess(x=data.coords[coord], y=data.data).items()
        }


class PolynomialModel(Model):
    def __init__(self, *, degree: int, prefix: str) -> None:
        if degree <= 0:
            raise ValueError(f'Degree must be positive, got: {degree}')
        super().__init__(
            prefix=prefix, param_names=(f'a{i}' for i in range(degree + 1))
        )

    @property
    def degree(self) -> int:
        return len(self._param_names) - 1

    def _call(self, x: sc.Variable, params: dict[str, sc.Variable]) -> sc.Variable:
        # The loop is rather complex to ensure that `val` has the correct shape after
        # broadcasting (assuming that all params have the same shape).
        val = params[f'a{self.degree}'] * x
        for i in range(self.degree - 1, 0, -1):
            val += params[f'a{i}']
            val *= x
        val += params['a0']
        return val

    def _guess(self, x: sc.Variable, y: sc.Variable) -> dict[str, sc.Variable]:
        poly = np.polynomial.Polynomial.fit(x.values, y.values, deg=self.degree)
        return {
            f'a{i}': sc.scalar(c, unit=y.unit / x.unit**i)
            for i, c in enumerate(poly.convert().coef)
        }


class GaussianModel(Model):
    def __init__(self, *, prefix: str) -> None:
        super().__init__(prefix=prefix, param_names=('amplitude', 'loc', 'scale'))

    def _call(self, x: sc.Variable, params: dict[str, sc.Variable]) -> sc.Variable:
        amplitude = params['amplitude']
        loc = params['loc']
        scale = params['scale']

        # Avoid division by 0
        scale = sc.scalar(
            max(scale.value, 1e-15), variance=scale.variance, unit=scale.unit
        )

        val = -((x - loc) ** 2)
        val /= 2 * scale**2
        val = sc.exp(val, out=val)
        val *= amplitude / (math.sqrt(2 * math.pi) * scale)
        return val

    def _guess(self, x: sc.Variable, y: sc.Variable) -> dict[str, sc.Variable]:
        params = {name: param for name, param in _guess_from_peak(x, y).items()}

        params['amplitude'] *= math.sqrt(2 * math.pi)
        return params


class LorentzianModel(Model):
    def __init__(self, *, prefix: str) -> None:
        super().__init__(prefix=prefix, param_names=('amplitude', 'loc', 'scale'))

    def _call(self, x: sc.Variable, params: dict[str, sc.Variable]) -> sc.Variable:
        amplitude = params['amplitude']
        loc = params['loc']
        scale = params['scale']

        # Use `max` to avoid division by 0
        val = (x - loc) ** 2
        val += (
            sc.scalar(max(scale.value, 1e-15), variance=scale.variance, unit=scale.unit)
            ** 2
        )
        val = sc.reciprocal(val, out=val)
        val *= amplitude * scale / math.pi
        return val

    def _guess(self, x: sc.Variable, y: sc.Variable) -> dict[str, sc.Variable]:
        params = {name: param for name, param in _guess_from_peak(x, y).items()}
        # Fudge factor taken from lmfit.
        # Not sure where exactly it comes from, but it is related to the normalization
        # of a Lorentzian and is approximately
        # 3.0 * math.pi / math.sqrt(2 * math.pi)
        params['amplitude'] *= 3.75
        return params


def _guess_from_peak(x: sc.Variable, y: sc.Variable) -> dict[str, sc.Variable]:
    """Estimate the parameters of a peaked function.

    The estimation is based on a Gaussian but
    is good enough for similar functions, too.

    The function was adapted from ``lmfit.models.guess_from_peak``, see
    https://github.com/lmfit/lmfit-py/blob/e57aab2fe2059efc07535a67e4fdc577291e9067/lmfit/models.py#L42
    """
    y_min, y_max = sc.min(y), sc.max(y)

    # These are the points within FWHM of the peak.
    x_half_max = x[y > (y_max + y_min) / 2.0]
    if len(x_half_max) > 2:
        loc = x_half_max.mean()
        # Rough estimate of sigma ~ FWHM / 2.355 for Gaussian.
        # Exact gamma = FWHM / 2 for Lorentzian.
        scale = (x_half_max.max() - x_half_max.min()) / 2.0
    else:
        loc = x[np.argmax(y.values)]
        # 6.0 taken from lmfit, don't know where it comes from.
        scale = (sc.max(x) - sc.min(x)) / 6.0

    amplitude = scale * (y_max - y_min)
    # TODO lower bound for sigma
    #   also for amplitude in the actual peak fit but not necessarily here
    return {
        'amplitude': amplitude,
        'loc': loc,
        'scale': scale,
    }
