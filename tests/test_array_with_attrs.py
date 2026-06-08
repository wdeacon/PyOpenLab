"""Tests for pyopenlab.utils.array_with_attrs.

Covers the AttributeDict / ArrayWithAttrs metadata plumbing, including a
regression test for ``attribute_bundler`` (which previously returned ``None``
because the inner function was never returned).
"""
import numpy as np
import pytest

from pyopenlab.utils.array_with_attrs import ArrayWithAttrs
from pyopenlab.utils.array_with_attrs import attribute_bundler
from pyopenlab.utils.array_with_attrs import AttributeDict
from pyopenlab.utils.array_with_attrs import DummyHDF5Group
from pyopenlab.utils.array_with_attrs import ensure_attribute_dict
from pyopenlab.utils.array_with_attrs import ensure_attrs


def test_attribute_dict_create_and_modify():
    d = AttributeDict()
    d.create('foo', 1)
    assert d['foo'] == 1
    d.modify('foo', 2)
    assert d['foo'] == 2


def test_attribute_dict_copy_arrays_breaks_reference():
    arr = np.array([1, 2, 3])
    d = AttributeDict({'a': arr, 'b': 5})
    d.copy_arrays()
    # The stored array must be a copy, so mutating the original does not leak in.
    arr[0] = 99
    assert d['a'][0] == 1
    assert d['b'] == 5


def test_ensure_attribute_dict_passthrough_and_copy():
    d = AttributeDict({'x': 1})
    # Already an AttributeDict and copy=False -> same object returned.
    assert ensure_attribute_dict(d) is d
    # copy=True -> a new AttributeDict with the same contents.
    copied = ensure_attribute_dict(d, copy=True)
    assert copied is not d
    assert copied == d
    # A plain dict is always wrapped.
    wrapped = ensure_attribute_dict({'y': 2})
    assert isinstance(wrapped, AttributeDict)
    assert wrapped['y'] == 2


def test_ensure_attrs_wraps_only_when_needed():
    plain = np.array([1, 2, 3])
    wrapped = ensure_attrs(plain)
    assert isinstance(wrapped, ArrayWithAttrs)
    # Something that already has attrs is returned unchanged.
    assert ensure_attrs(wrapped) is wrapped


def test_array_with_attrs_construction_and_attrs():
    a = ArrayWithAttrs(np.array([1, 2, 3, 4, 5]), attrs={'units': 'V'})
    assert isinstance(a, np.ndarray)
    assert isinstance(a.attrs, AttributeDict)
    assert a.attrs['units'] == 'V'


def test_array_with_attrs_slice_keeps_type_and_independent_attrs():
    a = ArrayWithAttrs(np.arange(5), attrs={'units': 'V'})
    s = a[2:4]
    assert isinstance(s, ArrayWithAttrs)
    # __array_finalize__ copies attrs, so the slice has its own dict.
    s.attrs['units'] = 'A'
    assert a.attrs['units'] == 'V'


def test_array_with_attrs_view_casting():
    b = np.array(10).view(ArrayWithAttrs)
    assert isinstance(b, ArrayWithAttrs)
    assert b == 10
    assert isinstance(b.attrs, AttributeDict)


def test_attribute_bundler_returns_working_callable():
    # Regression: attribute_bundler used to return None (missing return).
    bundler = attribute_bundler({'units': 'nm'})
    assert callable(bundler)
    out = bundler(np.array([1.0, 2.0, 3.0]))
    assert isinstance(out, ArrayWithAttrs)
    assert out.attrs['units'] == 'nm'
    np.testing.assert_array_equal(np.asarray(out), [1.0, 2.0, 3.0])


def test_dummy_hdf5_group_interface():
    g = DummyHDF5Group({'a': 1, 'b': 2}, attrs={'note': 'hi'}, name='grp')
    assert g['a'] == 1
    assert g['b'] == 2
    assert g.attrs['note'] == 'hi'
    assert g.name == 'grp'
    assert g.basename == 'grp'
    assert g.file is None
    assert g.parent is None
