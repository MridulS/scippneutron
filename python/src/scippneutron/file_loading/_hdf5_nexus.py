# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2021 Scipp contributors (https://github.com/scipp)
# @author Matthew Jones
import warnings

from typing import Union, Any, List, Optional, Tuple, Dict

import h5py
import h5py.h5a
import h5py.h5t
import numpy as np
import scipp as sc
from ._common import Group, MissingDataset, MissingAttribute


def _get_attr_as_str(h5_object, attribute_name: str):
    return _ensure_str(h5_object.attrs[attribute_name],
                       LoadFromHdf5.get_string_encoding(h5_object, attribute_name))


def _ensure_str(str_or_bytes: Union[str, bytes], encoding: str) -> str:
    """
    See https://docs.h5py.org/en/stable/strings.html for justification about some of
    the operations performed in this method. In particular, variable-length strings
    are returned as `str` from h5py, but need to be encoded using the surrogateescape
    error handler and then decoded using the encoding specified in the nexus file in
    order to get a correctly encoded string in all cases.

    Note also that the nexus standard leaves unspecified the behaviour of H5T_CSET_ASCII
    for characters >=128. Common extensions are the latin-1 ("extended ascii") character
    set which appear to be used in nexus files from some facilities. Attempt to load
    these strings with the latin-1 extended character set, but warn as this is
    technically unspecified behaviour.
    """
    if isinstance(str_or_bytes, str):
        str_or_bytes = str_or_bytes.encode('utf-8', 'surrogateescape')

    if encoding == "ascii":
        try:
            return str(str_or_bytes, encoding="ascii")
        except UnicodeDecodeError as e:
            decoded = str(str_or_bytes, encoding="latin-1")
            warnings.warn(f"Encoding for bytes '{str_or_bytes}' declared as ascii, "
                          f"but contains characters in extended ascii range. Assuming "
                          f"extended ASCII (latin-1), but this behaviour is not "
                          f"specified by the HDF5 or nexus standards and may therefore "
                          f"be incorrect. Decoded string using latin-1 is '{decoded}'. "
                          f"Error was '{str(e)}'.")
            return decoded
    else:
        return str(str_or_bytes, encoding)


_map_to_supported_type = {
    np.int8: np.int32,
    np.int16: np.int32,
    np.uint8: np.int32,
    np.uint16: np.int32,
    np.uint32: np.int32,
    np.uint64: np.int64,
}


def _ensure_supported_int_type(dataset_type: Any):
    try:
        return _map_to_supported_type[dataset_type]
    except KeyError:
        return dataset_type


class LoadFromHdf5:
    @staticmethod
    def find_by_nx_class(
            nx_class_names: Tuple[str, ...],
            root: Union[h5py.File, h5py.Group]) -> \
            Dict[str, List[Group]]:
        """
        Finds groups with requested NX_class in the subtree of root

        Returns a dictionary with NX_class name as the key and
        list of matching groups as the value
        """
        found_groups: Dict[str, List[Group]] = {
            class_name: []
            for class_name in nx_class_names
        }

        def _match_nx_class(_, h5_object):
            if LoadFromHdf5.is_group(h5_object):
                try:
                    nx_class = _get_attr_as_str(h5_object, "NX_class")
                    if nx_class in nx_class_names:
                        found_groups[nx_class].append(
                            Group(h5_object, h5_object.parent, h5_object.name))
                except KeyError:
                    pass

        root.visititems(_match_nx_class)
        # Also check if root itself is an NX_class
        _match_nx_class(None, root)
        return found_groups

    @staticmethod
    def dataset_in_group(group: h5py.Group, dataset_name: str) -> Tuple[bool, str]:
        if dataset_name not in group:
            return False, (f"Unable to load data from NXevent_data "
                           f"at '{group.name}' due to missing '{dataset_name}'"
                           f" field\n")
        return True, ""

    def load_dataset(self,
                     group: h5py.Group,
                     dataset_name: str,
                     dimensions: List[str],
                     dtype: Optional[Any] = None) -> sc.Variable:
        """
        Load an HDF5 dataset into a Scipp Variable
        :param group: Group containing dataset to load
        :param dataset_name: Name of the dataset to load
        :param dimensions: Dimensions for the output Variable
        :param dtype: Cast to this dtype during load,
          otherwise retain dataset dtype
        """
        try:
            dataset = group[dataset_name]
        except KeyError:
            raise MissingDataset()
        if dtype is None:
            dtype = _ensure_supported_int_type(dataset.dtype.type)
        variable = sc.empty(dims=dimensions,
                            shape=dataset.shape,
                            dtype=dtype,
                            unit=self.get_unit(dataset))
        dataset.read_direct(variable.values)
        return variable

    def load_dataset_from_group_as_numpy_array(self, group: h5py.Group,
                                               dataset_name: str):
        """
        Load a dataset into a numpy array
        Prefer use of load_dataset to load directly to a scipp variable,
        this function should only be used in rare cases that a
        numpy array is required.
        :param group: Group containing dataset to load
        :param dataset_name: Name of the dataset to load
        """
        try:
            dataset = group[dataset_name]
        except KeyError:
            raise MissingDataset()
        return self.load_dataset_as_numpy_array(dataset)

    @staticmethod
    def load_dataset_as_numpy_array(dataset: h5py.Dataset):
        """
        Load a dataset into a numpy array
        Prefer use of load_dataset to load directly to a scipp variable,
        this function should only be used in rare cases that a
        numpy array is required.
        :param dataset: The dataset to load values from
        """
        return dataset[...].astype(_ensure_supported_int_type(dataset.dtype.type))

    @staticmethod
    def get_dataset_numpy_dtype(group: h5py.Group, dataset_name: str) -> Any:
        return _ensure_supported_int_type(group[dataset_name].dtype.type)

    @staticmethod
    def get_name(group: Union[h5py.Group, h5py.Dataset]) -> str:
        """
        Just the name of this group, not the full path
        """
        return group.name.split("/")[-1]

    @staticmethod
    def get_unit(node: Union[h5py.Dataset, h5py.Group]) -> str:
        try:
            units = node.attrs["units"]
        except (AttributeError, KeyError):
            return "dimensionless"
        return _ensure_str(units, LoadFromHdf5.get_string_encoding(node, "units"))

    @staticmethod
    def get_child_from_group(group: Dict,
                             child_name: str) -> Union[h5py.Dataset, h5py.Group, None]:
        try:
            return group[child_name]
        except KeyError:
            return None

    def get_dataset_from_group(self, group: h5py.Group,
                               dataset_name: str) -> Optional[h5py.Dataset]:
        dataset = self.get_child_from_group(group, dataset_name)
        if not self.is_group(dataset):
            return dataset
        return None

    @staticmethod
    def load_scalar_string(group: h5py.Group, dataset_name: str) -> str:
        try:
            return _ensure_str(group[dataset_name][...].item(),
                               LoadFromHdf5.get_string_encoding(group, dataset_name))
        except KeyError:
            raise MissingDataset

    @staticmethod
    def get_string_encoding(group: h5py.Group, dataset_name: str):
        cset = h5py.h5a.get_info(group.id, dataset_name.encode("ascii")).cset

        if cset == h5py.h5t.CSET_ASCII:
            return "ascii"
        elif cset == h5py.h5t.CSET_UTF8:
            return "utf-8"
        else:
            warnings.warn(f"Unknown character set in HDF5 data file. Expected data "
                          f"types are {h5py.h5t.CSET_ASCII} (H5T_CSET_ASCII) or "
                          f"{h5py.h5t.CSET_UTF8} (H5T_CSET_UTF8) but got '{cset}'. "
                          f"Assuming data is UTF-8 encoded but this may be incorrect.")
            return "utf-8"

    @staticmethod
    def get_object_by_path(group: Union[h5py.Group, h5py.File],
                           path: str) -> h5py.Dataset:
        try:
            return group[path]
        except KeyError:
            raise MissingDataset

    @staticmethod
    def get_attribute_as_numpy_array(node: Union[h5py.Group, h5py.Dataset],
                                     attribute_name: str) -> np.ndarray:
        try:
            return np.asarray(node.attrs[attribute_name])
        except KeyError:
            raise MissingAttribute

    @staticmethod
    def get_attribute(node: Union[h5py.Group, h5py.Dataset],
                      attribute_name: str) -> Any:
        try:
            return node.attrs[attribute_name]
        except KeyError:
            raise MissingAttribute

    @staticmethod
    def get_string_attribute(node: Union[h5py.Group, h5py.Dataset],
                             attribute_name: str) -> str:
        try:
            return _ensure_str(node.attrs[attribute_name],
                               LoadFromHdf5.get_string_encoding(node, attribute_name))
        except KeyError:
            raise MissingAttribute

    @staticmethod
    def is_group(node: Any):
        # Note: Not using isinstance(node, h5py.Group) so we can support other
        # libraries that look like h5py but are not, in particular data
        # adapted from `tiled`.
        return hasattr(node, 'visititems')
