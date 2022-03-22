from .nexus_helpers import (
    NexusBuilder,
    EventData,
    Log,
    Monitor,
)
from .test_load_nexus import UTF8_TEST_STRINGS
import numpy as np
import pytest
from typing import Callable
import scipp as sc
from scippneutron import nexus


def open_nexus(builder: NexusBuilder):
    return builder.file


def open_json(builder: NexusBuilder):
    return builder.json


@pytest.fixture(params=[open_nexus, open_json])
def nexus_group(request):
    """
    Each test with this fixture is executed with load_nexus_json
    loading JSON output from the NexusBuilder, and with load_nexus
    loading in-memory NeXus output from the NexusBuilder
    """
    return request.param


def builder_with_events_monitor_and_log():
    event_time_offsets = np.array([456, 743, 347, 345, 632, 23], dtype='int64')
    event_data = EventData(
        event_id=np.array([1, 2, 3, 1, 3, 2]),
        event_time_offset=event_time_offsets,
        event_time_zero=np.array([
            1600766730000000000, 1600766731000000000, 1600766732000000000,
            1600766733000000000
        ]),
        event_index=np.array([0, 3, 3, 5]),
    )

    builder = NexusBuilder()
    builder.add_event_data(event_data)
    builder.add_event_data(event_data)
    builder.add_monitor(
        Monitor("monitor",
                data=np.array([1.]),
                axes=[("time_of_flight", np.array([1.]))]))
    builder.add_log(
        Log("log", np.array([1.1, 2.2, 3.3]), np.array([4.4, 5.5, 6.6]),
            value_units=''))
    return builder


def test_nxobject_root(nexus_group: Callable):
    with nexus_group(builder_with_events_monitor_and_log())() as f:
        root = nexus.NXroot(f)
        assert root.nx_class == nexus.NX_class.NXroot
        assert set(root.keys()) == {'entry', 'monitor'}


def test_nxobject_items(nexus_group: Callable):
    with nexus_group(builder_with_events_monitor_and_log())() as f:
        root = nexus.NXroot(f)
        items = root.items()
        assert len(items) == 2
        for k, v in items:
            if k == 'entry':
                assert v.nx_class == nexus.NX_class.NXentry
            else:
                assert k == 'monitor'
                assert v.nx_class == nexus.NX_class.NXmonitor


def test_nxobject_entry(nexus_group: Callable):
    with nexus_group(builder_with_events_monitor_and_log())() as f:
        entry = nexus.NXroot(f)['entry']
        assert entry.nx_class == nexus.NX_class.NXentry
        assert set(entry.keys()) == {'events_0', 'events_1', 'log'}


def test_nxobject_monitor(nexus_group: Callable):
    with nexus_group(builder_with_events_monitor_and_log())() as f:
        monitor = nexus.NXroot(f)['monitor']
        assert monitor.nx_class == nexus.NX_class.NXmonitor
        assert sc.identical(
            monitor[...],
            sc.DataArray(sc.array(dims=['time_of_flight'], values=[1.0]),
                         coords={
                             'time_of_flight':
                             sc.array(dims=['time_of_flight'], values=[1.0])
                         }))


def test_nxobject_log(nexus_group: Callable):
    with nexus_group(builder_with_events_monitor_and_log())() as f:
        log = nexus.NXroot(f)['entry']['log']
        assert log.nx_class == nexus.NX_class.NXlog
        assert sc.identical(
            log[...],
            sc.DataArray(
                sc.array(dims=['time'], values=[1.1, 2.2, 3.3]),
                coords={
                    'time':
                    sc.epoch(unit='ns') +
                    sc.array(dims=['time'], unit='s', values=[4.4, 5.5, 6.6]).to(
                        unit='ns', dtype='int64')
                }))


def test_nxobject_event_data(nexus_group: Callable):
    with nexus_group(builder_with_events_monitor_and_log())() as f:
        event_data = nexus.NXroot(f)['entry']['events_0']
        assert set(event_data.keys()) == set(
            ['event_id', 'event_index', 'event_time_offset', 'event_time_zero'])
        assert event_data.nx_class == nexus.NX_class.NXevent_data


def test_nxobject_getting_item_that_does_not_exists_raises_KeyError(
        nexus_group: Callable):
    with nexus_group(builder_with_events_monitor_and_log())() as f:
        root = nexus.NXroot(f)
        with pytest.raises(KeyError):
            root['abcde']


def test_nxobject_name_property_is_full_path(nexus_group: Callable):
    with nexus_group(builder_with_events_monitor_and_log())() as f:
        root = nexus.NXroot(f)
        assert root.name == '/'
        assert root['monitor'].name == '/monitor'
        assert root['entry'].name == '/entry'
        assert root['entry']['log'].name == '/entry/log'
        assert root['entry']['events_0'].name == '/entry/events_0'


def test_nxobject_grandchild_can_be_accessed_using_path(nexus_group: Callable):
    with nexus_group(builder_with_events_monitor_and_log())() as f:
        root = nexus.NXroot(f)
        assert root['entry/log'].name == '/entry/log'
        assert root['/entry/log'].name == '/entry/log'


def test_nxobject_by_nx_class_of_root_contains_everything(nexus_group: Callable):
    with nexus_group(builder_with_events_monitor_and_log())() as f:
        root = nexus.NXroot(f)
        classes = root.by_nx_class()
        assert list(classes[nexus.NX_class.NXentry]) == ['entry']
        assert list(classes[nexus.NX_class.NXmonitor]) == ['monitor']
        assert list(classes[nexus.NX_class.NXlog]) == ['log']
        assert set(classes[nexus.NX_class.NXevent_data]) == {'events_0', 'events_1'}


def test_nxobject_by_nx_class_contains_only_children(nexus_group: Callable):
    with nexus_group(builder_with_events_monitor_and_log())() as f:
        root = nexus.NXroot(f)
        classes = root['entry'].by_nx_class()
        assert list(classes[nexus.NX_class.NXentry]) == []
        assert list(classes[nexus.NX_class.NXmonitor]) == []
        assert list(classes[nexus.NX_class.NXlog]) == ['log']
        assert set(classes[nexus.NX_class.NXevent_data]) == set(
            ['events_0', 'events_1'])


def test_nxobject_dataset_items_are_returned_as_Field(nexus_group: Callable):
    with nexus_group(builder_with_events_monitor_and_log())() as f:
        field = nexus.NXroot(f)['entry/events_0/event_time_offset']
        assert isinstance(field, nexus.Field)


def test_field_properties(nexus_group: Callable):
    with nexus_group(builder_with_events_monitor_and_log())() as f:
        field = nexus.NXroot(f)['entry/events_0/event_time_offset']
        assert field.dtype == 'int64'
        assert field.name == '/entry/events_0/event_time_offset'
        assert field.shape == (6, )
        assert field.unit == sc.Unit('ns')


def test_field_dim_labels(nexus_group: Callable):
    with nexus_group(builder_with_events_monitor_and_log())() as f:
        event_data = nexus.NXroot(f)['entry/events_0']
        assert event_data['event_time_offset'].dims == ['event']
        assert event_data['event_time_zero'].dims == ['pulse']
        assert event_data['event_index'].dims == ['pulse']
        assert event_data['event_id'].dims == ['event']
        log = nexus.NXroot(f)['entry/log']
        assert log['time'].dims == ['time']
        assert log['value'].dims == ['time']
        monitor = nexus.NXroot(f)['monitor']
        assert monitor['time_of_flight'].dims == ['time_of_flight']
        assert monitor['data'].dims == ['time_of_flight']


def test_field_unit_is_none_if_no_units_attribute(nexus_group: Callable):
    builder = builder_with_events_monitor_and_log()
    builder.add_log(
        Log("mylog",
            np.array([1.1, 2.2, 3.3]),
            np.array([4.4, 5.5, 6.6]),
            value_units=None))
    with nexus_group(builder)() as f:
        field = nexus.NXroot(f)['entry/mylog']
        assert field.unit is None


def test_field_getitem_returns_variable_with_correct_size_and_values(
        nexus_group: Callable):
    with nexus_group(builder_with_events_monitor_and_log())() as f:
        field = nexus.NXroot(f)['entry/events_0/event_time_offset']
        assert sc.identical(
            field[...],
            sc.array(dims=['dim_0'],
                     unit='ns',
                     values=[456, 743, 347, 345, 632, 23],
                     dtype='int64'))
        assert sc.identical(
            field[1:],
            sc.array(dims=['dim_0'],
                     unit='ns',
                     values=[743, 347, 345, 632, 23],
                     dtype='int64'))
        assert sc.identical(
            field[:-1],
            sc.array(dims=['dim_0'],
                     unit='ns',
                     values=[456, 743, 347, 345, 632],
                     dtype='int64'))


@pytest.mark.parametrize("string", UTF8_TEST_STRINGS)
def test_field_of_utf8_encoded_dataset_is_loaded_correctly(nexus_group: Callable,
                                                           string):
    builder = NexusBuilder()
    if nexus_group == open_nexus:
        builder.add_title(np.array([string, string + string], dtype=object))
    else:  # json encodes itself
        builder.add_title(np.array([string, string + string]))
    with nexus_group(builder)() as f:
        title = nexus.NXroot(f)['entry/title']
        assert sc.identical(title[...],
                            sc.array(dims=['dim_0'], values=[string, string + string]))


def test_field_of_extended_ascii_in_ascii_encoded_dataset_is_loaded_correctly():
    nexus_group = open_nexus
    builder = NexusBuilder()
    # When writing, if we use bytes h5py will write as ascii encoding
    # 0xb0 = degrees symbol in latin-1 encoding.
    string = b"run at rot=90" + bytes([0xb0])
    builder.add_title(np.array([string, string + b'x']))
    with nexus_group(builder)() as f:
        title = nexus.NXroot(f)['entry/title']
        assert sc.identical(
            title[...],
            sc.array(dims=['dim_0'], values=["run at rot=90°", "run at rot=90°x"]))


def test_negative_event_index_converted_to_num_event(nexus_group: Callable):
    event_time_offsets = np.array([456, 743, 347, 345, 632, 23])
    event_data = EventData(
        event_id=np.array([1, 2, 3, 1, 3, 2]),
        event_time_offset=event_time_offsets,
        event_time_zero=np.array([
            1600766730000000000, 1600766731000000000, 1600766732000000000,
            1600766733000000000
        ]),
        event_index=np.array([0, 3, 3, -1000]),
    )

    builder = NexusBuilder()
    builder.add_event_data(event_data)
    with nexus_group(builder)() as f:
        root = nexus.NXroot(f)
        events = root['entry/events_0'][...]
        assert events.bins.size().values[2] == 3
        assert events.bins.size().values[3] == 0


def builder_with_events_and_events_monitor_without_event_id():
    event_time_offsets = np.array([456, 743, 347, 345, 632, 23])
    event_data = EventData(
        event_id=None,
        event_time_offset=event_time_offsets,
        event_time_zero=np.array([
            1600766730000000000, 1600766731000000000, 1600766732000000000,
            1600766733000000000
        ]),
        event_index=np.array([0, 3, 3, 5]),
    )

    builder = NexusBuilder()
    builder.add_event_data(event_data)
    builder.add_monitor(
        Monitor("monitor", data=np.array([1.]), axes=[], events=event_data))
    return builder


def test_event_data_without_event_id_can_be_loaded(nexus_group: Callable):
    with nexus_group(builder_with_events_and_events_monitor_without_event_id())() as f:
        event_data = nexus.NXroot(f)['entry/events_0']
        da = event_data[...]
        assert len(da.bins.coords) == 1
        assert 'event_time_offset' in da.bins.coords


def test_event_mode_monitor_without_event_id_can_be_loaded(nexus_group: Callable):
    with nexus_group(builder_with_events_and_events_monitor_without_event_id())() as f:
        monitor = nexus.NXroot(f)['monitor']
        da = monitor[...]
        assert len(da.bins.coords) == 1
        assert 'event_time_offset' in da.bins.coords
