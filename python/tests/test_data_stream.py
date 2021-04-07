from scippneutron.data_stream import _data_stream
from scippneutron._streaming_data_buffer import StreamedDataBuffer
import asyncio
import pytest
from typing import List
from streaming_data_types import serialise_ev42
import numpy as np


class FakeConsumer:
    """
    Use in place of KafkaConsumer to avoid having to do
    network IO in unit tests. Does not need to supply
    fake messages as the new_data method on the
    StreamedDataBuffer can be called manually instead.
    """
    def __init__(self):
        self.stopped = True

    def start(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


def stop_consumers(consumers: List[FakeConsumer]):
    for consumer in consumers:
        consumer.stop()


# Short time to use for buffer emit and data_stream interval in tests
# pass or fail fast!
SHORT_TEST_INTERVAL = 0.001  # 1 ms


@pytest.mark.asyncio
async def test_data_stream_returns_data_from_single_event_message():
    queue = asyncio.Queue()
    buffer = StreamedDataBuffer(queue, interval_s=SHORT_TEST_INTERVAL)
    consumers = [FakeConsumer()]
    time_of_flight = np.array([1., 2., 3.])
    detector_ids = np.array([4, 5, 6])
    test_message = serialise_ev42("detector", 0, 0, time_of_flight,
                                  detector_ids)
    await buffer.new_data(test_message)

    async for data in _data_stream(
            buffer,
            queue,
            consumers,  # type: ignore
            interval_s=SHORT_TEST_INTERVAL):
        assert np.allclose(data.coords['tof'].values, time_of_flight)

        # Cause the data_stream generator to stop and exit the "async for"
        stop_consumers(consumers)


@pytest.mark.asyncio
async def test_data_stream_returns_data_from_multiple_event_messages():
    queue = asyncio.Queue()
    buffer = StreamedDataBuffer(queue, interval_s=SHORT_TEST_INTERVAL)
    consumers = [FakeConsumer()]
    first_tof = np.array([1., 2., 3.])
    first_detector_ids = np.array([4, 5, 6])
    first_test_message = serialise_ev42("detector", 0, 0, first_tof,
                                        first_detector_ids)
    second_tof = np.array([1., 2., 3.])
    second_detector_ids = np.array([4, 5, 6])
    second_test_message = serialise_ev42("detector", 0, 0, second_tof,
                                         second_detector_ids)
    await buffer.new_data(first_test_message)
    await buffer.new_data(second_test_message)

    async for data in _data_stream(
            buffer,
            queue,
            consumers,  # type: ignore
            interval_s=SHORT_TEST_INTERVAL):
        expected_tofs = np.concatenate((first_tof, second_tof))
        assert np.allclose(data.coords['tof'].values, expected_tofs)

        stop_consumers(consumers)


@pytest.mark.asyncio
async def test_warn_on_data_emit_if_unrecognised_message_was_encountered():
    queue = asyncio.Queue()
    buffer = StreamedDataBuffer(queue, interval_s=SHORT_TEST_INTERVAL)
    # First 4 bytes of the message payload are the FlatBuffer schema identifier
    # "abcd" does not correspond to a FlatBuffer schema for data
    # that scipp is interested in
    test_message = b"abcd0000"
    await buffer.new_data(test_message)

    with pytest.warns(UserWarning):
        await buffer._emit_data()


# TODO tests for:
#  exceed buffer size with multiple messages
#  exceed buffer size with single message
