"""NumPy array subclass that carries HDF5-compatible metadata attributes."""

import numpy as np


class AttributeDict(dict):
    """A dict with ``create`` and ``modify`` methods for h5py attrs compatibility."""

    def create(self, name, data):
        """Set ``name`` to ``data``, mirroring the h5py attrs ``create`` interface."""
        self[name] = data

    def modify(self, name, data):
        """Update ``name`` to ``data``, mirroring the h5py attrs ``modify`` interface."""
        self[name] = data

    def copy_arrays(self):
        """Replace any numpy.ndarray in the dict with a copy, to break any unintentional links."""
        for k in list(self.keys()):
            if isinstance(self[k], np.ndarray):
                self[k] = np.copy(self[k])


def ensure_attribute_dict(obj, copy=False):
    """Return an AttributeDict from a mapping, copying data if requested.

    Args:
        obj: The mapping to convert or wrap.
        copy: If True, return a new AttributeDict with any numpy array values
            copied to break unintentional references.

    Returns:
        AttributeDict: The original object if it is already an AttributeDict
        and ``copy`` is False, otherwise a new one containing the same data.
    """
    if isinstance(obj, AttributeDict) and not copy:
        return obj
    else:
        out = AttributeDict(obj)
        if copy:
            out.copy_arrays()
        return out


def ensure_attrs(obj):
    """Ensure an object has an ``attrs`` dict, wrapping it in ArrayWithAttrs if not.

    Args:
        obj: An array-like object, optionally already carrying ``.attrs``.

    Returns:
        ArrayWithAttrs | original: The original object if it already has
        ``.attrs``, otherwise a new :class:`ArrayWithAttrs` wrapping it.
    """
    if hasattr(obj, 'attrs'):
        return obj  #if it has attrs, do nothing
    else:
        return ArrayWithAttrs(obj)  #otherwise, wrap it


class ArrayWithAttrs(np.ndarray):
    """A numpy ndarray with an :class:`AttributeDict` accessible as ``.attrs``.

    Intended as a lightweight stand-in for an h5py dataset, allowing metadata
    to travel alongside array data through pyopenlab pipelines.
    """

    def __new__(cls, input_array, attrs={}):
        """Create an ArrayWithAttrs from an existing array.

        Args:
            input_array: Array-like to wrap. Data is not copied if avoidable.
            attrs: Metadata dict to attach. Defaults to an empty dict.

        Returns:
            ArrayWithAttrs: The new array with ``.attrs`` populated.
        """
        # the input array should be a numpy array, then we cast it to this type
        obj = np.asarray(input_array).view(cls)
        # next, add the dict
        # ensure_attribute_dict always returns an AttributeDict
        obj.attrs = ensure_attribute_dict(attrs)
        # return the new object
        return obj

    def __array_finalize__(self, obj):
        """Propagate ``.attrs`` when NumPy creates a derived array."""
        # this is called by numpy when the object is created (__new__ may or
        # may not get called)
        if obj is None:
            return  # if obj is None, __new__ was called - do nothing
        # if we didn't create the object with __new__,  we must add the attrs
        # dictionary.  We copy this from the source object if possible (while
        # ensuring it's the right type) or create a new, empty one if not.
        # NB we don't use ensure_attribute_dict because we want to make sure the
        # dict object is *copied* not merely referenced.
        self.attrs = ensure_attribute_dict(getattr(obj, 'attrs', {}), copy=True)


def attribute_bundler(attrs):
    """Return a function that wraps an array with the given attributes.

    Args:
        attrs: Metadata dict to attach to arrays.

    Returns:
        Callable: A function that accepts an array and returns an
        :class:`ArrayWithAttrs` with ``attrs`` attached.
    """

    def bundle_attrs(array):
        return ArrayWithAttrs(array, attrs=attrs)

    return bundle_attrs


class DummyHDF5Group(dict):
    """A dict that mimics an h5py Group for testing and offline data handling.

    Exposes ``.attrs``, ``.name``, ``.basename``, ``.file``, and ``.parent``
    to satisfy h5py Group interfaces without requiring an open HDF5 file.
    """

    def __init__(self, dictionary, attrs={}, name="DummyHDF5Group"):
        """Create a DummyHDF5Group from a dictionary.

        Args:
            dictionary: Initial key-value pairs to populate the group.
            attrs: Metadata attributes dict.
            name: Name/path string for the group.
        """
        super(DummyHDF5Group, self).__init__()
        self.attrs = attrs
        for key in dictionary:
            self[key] = dictionary[key]
        self.name = name
        self.basename = name

    file = None
    parent = None
