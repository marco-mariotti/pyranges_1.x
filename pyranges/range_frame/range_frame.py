import inspect
from collections.abc import Callable, Iterable
from functools import cached_property
from typing import Any

import pandas as pd

from pyranges.names import (
    RANGE_COLS,
    SKIP_IF_DF_EMPTY_DEFAULT,
    SKIP_IF_DF_EMPTY_TYPE,
    SKIP_IF_EMPTY_ANY,
    SKIP_IF_EMPTY_BOTH,
    SKIP_IF_EMPTY_LEFT,
    SKIP_IF_EMPTY_RIGHT,
    VALID_BY_TYPES,
    VALID_OVERLAP_TYPE,
    BinaryOperation,
    UnaryOperation,
)
from pyranges.range_frame.range_frame_validator import InvalidRangesReason
from pyranges.tostring import tostring


def should_skip_operation(df: pd.DataFrame, *, df2: pd.DataFrame, skip_if_empty: SKIP_IF_DF_EMPTY_TYPE) -> bool:
    """Whether to skip operation because one or more dfs are empty."""
    if df.empty and df2.empty:
        return skip_if_empty in {SKIP_IF_EMPTY_BOTH, SKIP_IF_EMPTY_ANY, SKIP_IF_EMPTY_LEFT, SKIP_IF_EMPTY_RIGHT}
    if df.empty:
        return skip_if_empty in {SKIP_IF_EMPTY_LEFT, SKIP_IF_EMPTY_ANY}
    if df2.empty:
        return skip_if_empty in {SKIP_IF_EMPTY_RIGHT, SKIP_IF_EMPTY_ANY}
    return False


class RangeFrame(pd.DataFrame):
    """Class for range based operations."""

    def __new__(cls, *args, **kwargs) -> "RangeFrame | pd.DataFrame":  # type: ignore[misc]
        """Create a new instance of a PyRanges object."""
        # __new__ is a special static method used for creating and
        # returning a new instance of a class. It is called before
        # __init__ and is typically used in scenarios requiring
        # control over the creation of new instances

        if not args:
            return super().__new__(cls)
        if not kwargs:
            return super().__new__(cls)

        df = pd.DataFrame(kwargs.get("data") or (args[0]))

        missing_any_required_columns = not set(RANGE_COLS).issubset(df.columns)
        if missing_any_required_columns:
            return df

        return super().__new__(cls)

    @property
    def _constructor(self) -> type:
        return RangeFrame

    @cached_property
    def _required_columns(self) -> Iterable[str]:
        return RANGE_COLS[:]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        missing_columns = [c for c in RANGE_COLS if c not in self.columns]
        if missing_columns:
            msg = f"Missing required columns: {missing_columns}"
            raise ValueError(msg)

    def __str__(
        self,
        **kwargs: int | None,
    ) -> str:  # , max_col_width: int | None = None, max_total_width: int | None = None) -> str:
        """Return string representation."""
        str_repr = tostring(
            self,
            max_col_width=kwargs.get("max_col_width"),
            max_total_width=kwargs.get("max_total_width"),
        )
        if reasons := InvalidRangesReason.formatted_reasons_list(self):
            return f"{str_repr}\nInvalid ranges:\n{reasons}"
        return str_repr

    def __repr__(self, max_col_width: int | None = None, max_total_width: int | None = None) -> str:
        return self.__str__(max_col_width=max_col_width, max_total_width=max_total_width)

    def overlap(
        self,
        other: "RangeFrame",
        how: VALID_OVERLAP_TYPE = "first",
        by: VALID_BY_TYPES = None,
        **_,
    ) -> "RangeFrame":
        """Find intervals in self overlapping other..

        Parameters
        ----------
        other
            Other ranges to find overlaps with.
        how
            How to find overlaps. "first" finds the first overlap, "containment" finds all overlaps
            where self is contained in other, and "all" finds all overlaps.
        by:
            Grouping columns. If None, all columns are used.

        Returns
        -------
        RangeFrame
            RangeFrame with overlapping ranges.

        Examples
        --------
        >>> import pyranges as pr
        >>> r = pr.RangeFrame({"Start": [1, 1, 2, 2], "End": [3, 3, 5, 4], "Id": list("abad")})
        >>> r
          index  |      Start      End  Id
          int64  |      int64    int64  object
        -------  ---  -------  -------  --------
              0  |          1        3  a
              1  |          1        3  b
              2  |          2        5  a
              3  |          2        4  d
        RangeFrame with 4 rows, 3 columns, and 1 index columns.

        >>> r2 = pr.RangeFrame({"Start": [0, 2], "End": [1, 20], "Id": list("ad")})
        >>> r2
          index  |      Start      End  Id
          int64  |      int64    int64  object
        -------  ---  -------  -------  --------
              0  |          0        1  a
              1  |          2       20  d
        RangeFrame with 2 rows, 3 columns, and 1 index columns.

        >>> r.overlap(r2, how="first")
          index  |      Start      End  Id
          int64  |      int64    int64  object
        -------  ---  -------  -------  --------
              0  |          1        3  a
              1  |          1        3  b
              2  |          2        5  a
              3  |          2        4  d
        RangeFrame with 4 rows, 3 columns, and 1 index columns.

        >>> r.overlap(r2, how="containment")
          index  |      Start      End  Id
          int64  |      int64    int64  object
        -------  ---  -------  -------  --------
              2  |          2        5  a
              3  |          2        4  d
        RangeFrame with 2 rows, 3 columns, and 1 index columns.

        >>> r.overlap(r2, how="all")
          index  |      Start      End  Id
          int64  |      int64    int64  object
        -------  ---  -------  -------  --------
              0  |          1        3  a
              1  |          1        3  b
              2  |          2        5  a
              3  |          2        4  d
        RangeFrame with 4 rows, 3 columns, and 1 index columns.

        >>> r.overlap(r2, how="all", by="Id")
          index  |      Start      End  Id
          int64  |      int64    int64  object
        -------  ---  -------  -------  --------
              3  |          2        4  d
        RangeFrame with 1 rows, 3 columns, and 1 index columns.
        """
        from pyranges.methods.overlap import _overlap

        return self.apply_pair(other, _overlap, how=how, by=by)

    def apply_single(
        self,
        function: UnaryOperation,
        by: VALID_BY_TYPES,
        *,
        preserve_index: bool = False,
        **kwargs: Any,
    ) -> "RangeFrame":
        """Call a function on a RangeFrame.

        Parameters
        ----------
        function: Callable
            Function to call.

        by: str or list of str
            Group by these columns.

        preserve_index: bool
            Preserve the original index. Only valid if the function returns the index cols.

        kwargs: dict
            Passed to function.
        """
        assert_valid_ranges(function, self)

        if not by:
            return _mypy_ensure_rangeframe(function(self, **kwargs))
        by = self._by_to_list(by)

        if not preserve_index:
            return _mypy_ensure_rangeframe(self.groupby(by).apply(function, by=by, **kwargs).reset_index(drop=True))

        preserve_index_col = "__old_index__"

        self[preserve_index_col] = self.index
        result = self.groupby(by).apply(function, by=by, **kwargs).reset_index(drop=True)
        result = result.set_index(preserve_index_col)
        if isinstance(self.index, pd.MultiIndex):
            result.index.names = self.index.names
        else:
            result.index.name = self.index.name
        self = self.drop(preserve_index_col, axis="columns")
        return _mypy_ensure_rangeframe(result)

    def apply_pair(
        self,
        other: "RangeFrame",
        function: BinaryOperation,
        by: VALID_BY_TYPES = None,
        skip_if_empty: SKIP_IF_DF_EMPTY_TYPE = SKIP_IF_DF_EMPTY_DEFAULT,
        **kwargs,
    ) -> "RangeFrame":
        """Call a function on two RangeFrames.

        Parameters
        ----------
        other: RangeFrame
            Other RangeFrame.

        function: Callable
            Function to call.

        by: str or list of str, default None
            Group by these columns.

        kwargs: dict
            Passed to function.

        skip_if_empty:
            Whether to skip the operations if one of the dataframes is empty for a particular group.

        Examples
        --------
        >>> import pyranges as pr
        >>> r = pr.RangeFrame({"Start": [1, 1, 4, 2], "End": [3, 3, 5, 4], "Id": list("abad")})
        >>> bad, ok = r, r.copy()
        >>> bad.loc[0, "Start"] = -1  # make r invalid
        >>> bad.apply_pair(ok, lambda x, y: x)
        Traceback (most recent call last):
        ...
        ValueError: Cannot perform function on invalid ranges (function was bad.apply_pair(ok, lambda x, y: x)).
        >>> from pyranges.methods.overlap import _overlap
        >>> ok.apply_pair(bad, _overlap)
        Traceback (most recent call last):
        ...
        ValueError: Cannot perform function on invalid ranges (function was _overlap).
        """
        assert_valid_ranges(function, self, other)
        if by is None:
            return _mypy_ensure_rangeframe(function(self, other, **kwargs))

        by = self._by_to_list(by)
        results = []
        empty = RangeFrame(columns=other.columns)
        others = dict(list(other.groupby(by)))

        for key, _df in self.groupby(by):
            odf = others.get(key, empty)

            if should_skip_operation(_df, df2=odf, skip_if_empty=skip_if_empty):
                continue
            results.append(function(_mypy_ensure_rangeframe(_df), _mypy_ensure_rangeframe(odf), **kwargs))

        return _mypy_ensure_rangeframe(pd.concat(results))

    def sort_by_position(self) -> "RangeFrame":
        """Sort by Start and End columns."""
        return _mypy_ensure_rangeframe(self.sort_values(RANGE_COLS))

    @staticmethod
    def _by_to_list(by: str | Iterable[str] | None) -> list[str]:
        return [by] if isinstance(by, str) else ([*by] if by is not None else [])

    def reasons_why_frame_is_invalid(self) -> list[InvalidRangesReason] | None:  # noqa: D102
        __doc__ = InvalidRangesReason.is_invalid_ranges_reasons.__doc__  # noqa: A001, F841

        return InvalidRangesReason.is_invalid_ranges_reasons(self)

    def copy(self, *args, **kwargs) -> "RangeFrame":  # noqa: D102
        return _mypy_ensure_rangeframe(super().copy(*args, **kwargs))

    def drop(self, *args, **kwargs) -> "RangeFrame | None":  # type: ignore[override]  # noqa: D102
        return self.__class__(super().drop(*args, **kwargs))

    def drop_and_return[T: "RangeFrame"](self: T, *args: Any, **kwargs: Any) -> T:  # noqa: PYI019, D102
        kwargs["inplace"] = False
        return self.__class__(super().drop(*args, **kwargs))

    def reindex(self, *args, **kwargs) -> "RangeFrame":  # noqa: D102
        return self.__class__(super().reindex(*args, **kwargs))


def _mypy_ensure_rangeframe(r: pd.DataFrame) -> "RangeFrame":
    result = RangeFrame(r)
    if not isinstance(result, RangeFrame):
        msg = f"Expected RangeFrame, got {type(result)}"
        raise TypeError(msg)
    return result


def assert_valid_ranges(function: Callable, *args: "RangeFrame") -> None:
    """Raise ValueError because function is called on invalid ranges."""
    if any(r.reasons_why_frame_is_invalid() for r in args):
        is_not_lambda = function.__name__ != "<lambda>"
        function_repr = function.__name__ if is_not_lambda else inspect.getsource(function).strip()
        msg = f"Cannot perform function on invalid ranges (function was {function_repr})."
        raise ValueError(msg)