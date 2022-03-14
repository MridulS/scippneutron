# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2022 Scipp contributors (https://github.com/scipp)
# @author Matthew Jones

from typing import Union, Tuple, Dict, List
import h5py
import scipp as sc
import numpy as np


class BadSource(Exception):
    """
    Raise if something is wrong with data source which
    prevents it being used. Warn the user.
    """
    pass


class SkipSource(Exception):
    """
    Raise to abort using the data source, do not
    warn the user.
    """
    pass


class MissingDataset(Exception):
    pass


class MissingAttribute(Exception):
    pass


class JSONGroup(dict):
    def __init__(self, parent: dict, name: str, file: dict, group: dict):
        super().__init__(**group)
        self.parent = parent
        self.name = name
        self.file = file


Dataset = Union[h5py.Dataset, Dict]
Group = Union[h5py.Group, JSONGroup]


def convert_time_to_datetime64(
        raw_times: sc.Variable,
        group_path: str,
        start: str = None,
        scaling_factor: Union[float, np.float_] = None) -> sc.Variable:
    """
    The nexus standard allows an arbitrary scaling factor to be inserted
    between the numbers in the `time` series and the unit of time reported
    in the nexus attribute.

    The times are also relative to a given log start time, which might be
    different for each log. If this log start time is not available, the start of the
    unix epoch (1970-01-01T00:00:00Z) is used instead.

    See https://manual.nexusformat.org/classes/base_classes/NXlog.html

    Args:
        raw_times: The raw time data from a nexus file.
        group_path: The path within the nexus file to the log being read.
            Used to generate warnings if loading the log fails.
        start: Optional, the start time of the log in an ISO8601
            string. If not provided, defaults to the beginning of the
            unix epoch (1970-01-01T00:00:00Z).
        scaling_factor: Optional, the scaling factor between the provided
            time series data and the unit of the raw_times Variable. If
            not provided, defaults to 1 (a no-op scaling factor).
    """
    try:
        raw_times_ns = sc.to_unit(raw_times, sc.units.ns, copy=False)
    except sc.UnitError:
        raise BadSource(f"The units of time in the entry at "
                        f"'{group_path}/time{{units}}' must be convertible to seconds, "
                        f"but this cannot be done for '{raw_times.unit}'. Skipping "
                        f"loading group at '{group_path}'.")

    try:
        _start_ts = sc.scalar(value=np.datetime64(start or "1970-01-01T00:00:00Z"),
                              unit=sc.units.ns,
                              dtype=sc.DType.datetime64)
    except ValueError:
        raise BadSource(
            f"The date string '{start}' in the entry at "
            f"'{group_path}/time@start' failed to parse as an ISO8601 date. "
            f"Skipping loading group at '{group_path}'")

    if scaling_factor is None:
        times = raw_times_ns.astype(sc.DType.int64, copy=False)
    else:
        _scale = sc.scalar(value=scaling_factor)
        times = (raw_times_ns * _scale).astype(sc.DType.int64, copy=False)
    return _start_ts + times


# Note that scipp does not support dicts yet, but this HDF5 code does, to
# allow for loading blocks of 2d (or higher) data efficiently.
ScippIndex = Union[type(Ellipsis), int, slice, Tuple[str, Union[int, slice]],
                   Dict[str, Union[int, slice]]]


def _to_canonical_select(dims: List[str], select: ScippIndex) -> ScippIndex:
    """Return selection as dict with explicit dim labels"""
    def check_1d():
        if len(dims) != 1:
            raise ValueError(f"Dataset has multiple dimensions {dims}, "
                             "specify the dimension to index.")

    if select is Ellipsis:
        return {}
    if isinstance(select, tuple) and len(select) == 0:
        return {}
    if isinstance(select, tuple) and isinstance(select[0], str):
        key, sel = select
        return {key: sel}
    if isinstance(select, tuple):
        check_1d()
        if len(select) != 1:
            raise ValueError(f"Dataset has single dimension {dims}, "
                             "but multiple indices {select} were specified.")
        return {dims[0]: select[0]}
    elif isinstance(select, int) or isinstance(select, slice):
        check_1d()
        return {dims[0]: select}
    if not isinstance(select, dict):
        raise ValueError(f"Cannot process index {select}.")
    return select


def to_plain_index(dims: List[str], select: ScippIndex) -> Union[int, tuple]:
    """
    Given a valid "scipp" index 'select', return an equivalent plain numpy-style index.
    """
    select = _to_canonical_select(dims, select)
    index = [slice(None)] * len(dims)
    for key, sel in select.items():
        if key not in dims:
            raise ValueError(
                f"'{key}' used for indexing not found in dataset dims {dims}.")
        index[dims.index(key)] = sel
    if len(index) == 1:
        return index[0]
    return tuple(index)


def to_child_select(dims: List[str], child_dims: List[str],
                    select: ScippIndex) -> ScippIndex:
    """
    Given a valid "scipp" index 'select' for a Nexus class, return a selection for a
    child field of the class, which may have fewer dimensions.

    This removes any selections that apply to the parent but not the child.
    """
    if set(dims) == set(child_dims):
        return select
    select = _to_canonical_select(dims, select)
    for d in dims:
        if d not in child_dims and d in select:
            del select[d]
    return select


def add_position_and_transforms_to_data(data: Union[sc.DataArray,
                                                    sc.Dataset], transform_name: str,
                                        position_name: str, base_position_name: str,
                                        transforms: sc.Variable,
                                        positions: sc.Variable):
    if isinstance(data, sc.DataArray):
        coords = data.coords
        attrs = data.attrs
    else:
        coords = data
        attrs = data

    if transforms is None:
        coords[position_name] = positions
        attrs[base_position_name] = positions
    elif isinstance(transforms, sc.Variable):
        # If transform is not time-dependent.
        coords[position_name] = transforms * positions
        attrs[base_position_name] = positions
        attrs[transform_name] = sc.scalar(value=transforms)
    else:
        coords[base_position_name] = positions
        coords[transform_name] = sc.scalar(value=transforms)
