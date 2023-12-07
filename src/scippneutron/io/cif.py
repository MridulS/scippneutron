# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2023 Scipp contributors (https://github.com/scipp)
from __future__ import annotations

import io
import warnings
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Union

import scipp as sc


def save_cif(
    fname: Union[str, Path, io.TextIOBase], blocks: Union[Block, Iterable[Block]]
) -> None:
    """Save data blocks to a CIF file.

    Create :class:`cif.Block` objects to first collect and structure the data
    for the file, then use this function to write the file.

    Parameters
    ----------
    fname:
        Path or file handle for the output file.
    blocks:
        One or more CIF data blocks to write to the file.

    See also
    --------
    cif.Block.save:
        Method for saving a single block.
    """
    if isinstance(blocks, Block):
        blocks = (blocks,)
    with _open(fname) as f:
        _write_file_heading(f)
        _write_multi(f, blocks)


class Chunk:
    def __init__(
        self,
        pairs: Union[Mapping[str, Any], Iterable[tuple[str, Any]], None],
        /,
        *,
        comment: str = '',
    ) -> None:
        self._pairs = dict(pairs) if pairs is not None else {}
        self._comment = _encode_non_ascii(comment)

    @property
    def comment(self) -> str:
        return self._comment

    @comment.setter
    def comment(self, comment: str) -> None:
        self._comment = _encode_non_ascii(comment)

    def write(self, f: io.TextIOBase) -> None:
        _write_comment(f, self.comment)
        for key, val in self._pairs.items():
            v = _format_value(val)
            if v.startswith(';'):
                f.write(f'_{key}\n{v}\n')
            else:
                f.write(f'_{key} {v}\n')


class Loop:
    """A CIF loop.

    Contains a mapping from strings to Scipp variables.
    The strings are arbitrary and ``Loop`` can merge items from different categories
    into a single loop.
    All variables must have the same length.
    """

    def __init__(
        self,
        columns: Union[
            Mapping[str, sc.Variable], Iterable[tuple[str, sc.Variable]], None
        ],
        *,
        comment: str = '',
    ) -> None:
        """Create a new CIF loop.

        Parameters
        ----------
        columns:
            Defines a mapping from column names (including their category)
            to column values as Scipp variables.
        comment:
            Optional comment that can be written above the loop in the file.
        """
        self._columns = dict(columns) if columns is not None else {}
        self._comment = _encode_non_ascii(comment)

    @property
    def comment(self) -> str:
        return self._comment

    @comment.setter
    def comment(self, comment: str) -> None:
        self._comment = _encode_non_ascii(comment)

    def write(self, f: io.TextIOBase) -> None:
        _write_comment(f, self.comment)
        f.write('loop_\n')
        for key in self._columns:
            f.write(f'_{key}\n')
        formatted_values = [
            tuple(map(_format_value, row))
            for row in _strict_zip(*self._columns.values())
        ]
        sep = (
            '\n'
            if any(';' in item for row in formatted_values for item in row)
            else ' '
        )
        for row in formatted_values:
            f.write(sep.join(row))
            f.write('\n')


class Block:
    """A CIF data block.

    A block contains an ordered sequence of loops
    and chunks (groups of key-value-pairs).
    The contents are written to file in the order specified in the block.
    """

    def __init__(
        self,
        name: str,
        content: Optional[Iterable[Union[Mapping[str, Any], Loop, Chunk]]] = None,
        *,
        comment: str = '',
    ) -> None:
        """Create a new CIF data block.

        Parameters
        ----------
        name:
            Name of the block.
            Can contain any non-linebreak characters.
            Can be at most 75 characters long.
        content:
            Initial loops and chunks.
            ``dicts`` are converted to :class:`cif.Chunk`s.
        comment:
            Optional comment that can be written above the block in the file.
        """
        self._name = ''
        self.name = name
        self._content = _convert_input_content(content) if content is not None else []
        self._comment = _encode_non_ascii(comment)

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, name: str) -> None:
        self._name = _encode_non_ascii(name)
        if ' ' in self._name or '\t' in self._name or '\n' in self._name:
            raise ValueError(
                "Block name must not contain spaces or line breaks, "
                f"got: '{self._name}'"
            )
        if len(self._name) > 75:
            warnings.warn(
                "cif.Block name should not be longer than 75 characters, got "
                f"{len(self._name)} characters ('{self._name}')",
                UserWarning,
                stacklevel=2,
            )

    @property
    def comment(self) -> str:
        return self._comment

    @comment.setter
    def comment(self, comment: str) -> None:
        self._comment = _encode_non_ascii(comment)

    def add(
        self,
        content: Union[Mapping[str, Any], Iterable[tuple[str, Any]], Chunk],
        /,
        comment: str = '',
    ) -> None:
        if not isinstance(content, Chunk):
            content = Chunk(content, comment=comment)
        self._content.append(content)

    def write(self, f: io.TextIOBase) -> None:
        _write_comment(f, self.comment)
        f.write(f'data_{self.name}\n\n')
        _write_multi(f, self._content)

    def save(
        self,
        fname: Union[str, Path, io.TextIOBase],
    ) -> None:
        """Save this block to a CIF file.

        Equivalent to ``cif.save_cif(fname, self)``.

        Parameters
        ----------
        fname:
            Path or file handle for the output file.

        See also
        --------
        cif.save_cif:
            Free function for saving one or more blocks.
        """
        save_cif(fname, self)


def _convert_input_content(
    content: Iterable[Union[Mapping[str, Any], Loop, Chunk]]
) -> list[Union[Loop, Chunk]]:
    return [
        item if isinstance(item, (Loop, Chunk)) else Chunk(item) for item in content
    ]


@contextmanager
def _open(fname: Union[str, Path, io.TextIOBase]):
    if isinstance(fname, io.TextIOBase):
        yield fname
    else:
        with open(fname, 'w') as f:
            yield f


def _quotes_for_string_value(value: str) -> Optional[str]:
    if '\n' in value:
        return ';'
    if "'" in value:
        if '"' in value:
            return ';'
        return '"'
    if '"' in value:
        return "'"
    if ' ' in value:
        return "'"
    return None


def _encode_non_ascii(s: str) -> str:
    return s.encode('ascii', 'backslashreplace').decode('ascii')


def _format_value(value: Any) -> str:
    if isinstance(value, sc.Variable):
        if value.variance is not None:
            without_unit = sc.scalar(value.value, variance=value.variance)
            s = f'{without_unit:c}'
        else:
            s = str(value.value)
    elif isinstance(value, datetime):
        s = value.isoformat()
    else:
        s = str(value)

    s = _encode_non_ascii(s)

    if (quotes := _quotes_for_string_value(s)) == ';':
        return f'; {s}\n;'
    elif quotes is not None:
        return quotes + s + quotes
    return s


def _write_comment(f: io.TextIOBase, comment: str) -> None:
    if comment:
        f.write('# ')
        f.write('\n# '.join(comment.splitlines()))
        f.write('\n')


def _write_multi(f: io.TextIOBase, to_write: Iterable[Any]) -> None:
    first = True
    for item in to_write:
        if not first:
            f.write('\n')
        first = False
        item.write(f)


def _write_file_heading(f: io.TextIOBase) -> None:
    f.write('#\\#CIF_1.1\n')


def _strict_zip(*args: Iterable[Any]) -> Iterable[Any]:
    try:
        return zip(*args, strict=True)
    except TypeError:
        pass
    return zip(*args)
