"""HDF5 data file management for pyopenlab.

Provides :class:`DataFile` and :class:`Group`, subclasses of the h5py
equivalents that add auto-incrementing dataset names, creation timestamps,
metadata helpers, and a module-level "current file" registry used by
instruments to route data without explicit file handles.
"""

__author__ = "rwb27"

import datetime
import os
import os.path
import re
import sys

import h5py

try:
    from collections import Sequence
except ImportError:
    from collections.abc import Sequence

import numpy as np

from pyopenlab.utils.array_with_attrs import DummyHDF5Group
from pyopenlab.utils.show_gui_mixin import ShowGUIMixin
import pyopenlab.utils.version


def attributes_from_dict(group_or_dataset, dict_of_attributes):
    """Write a dictionary of values as HDF5 attributes on a group or dataset.

    Values that cannot be stored natively in HDF5 are coerced to strings with
    a warning printed to stdout.

    Args:
        group_or_dataset: The h5py Group or Dataset to annotate.
        dict_of_attributes: Attribute name → value mapping to write.
    """
    attrs = group_or_dataset.attrs
    for key, value in list(dict_of_attributes.items()):
        if value is not None:
            try:
                attrs[key] = value
            except TypeError:
                print(
                    "Warning, metadata {0}='{1}' can't be saved in HDF5.  Saving with str()".format(
                        key, value))
                attrs[key] = str(value)
    #group_or_dataset.attrs.update(dict_of_attributes) #We can't do this - we'd lose the error handling.


def h5_item_number(group_or_dataset):
    """Return the trailing integer in an HDF5 item's name, or None.

    Args:
        group_or_dataset: An h5py Group or Dataset.

    Returns:
        int | None: The number at the end of the name, or None if absent.
    """
    m = re.search(r"(\d+)$", group_or_dataset.name)  # match numbers at the end of the name
    return int(m.groups()[0]) if m else None


#TODO: merge with the current_datafile system
def get_data_dir(destination='local', rel_path='Desktop/Data'):
    """Return (and create if needed) a data storage directory.

    Args:
        destination: ``'local'`` (default) resolves relative to the home
            directory. ``'server'`` uses ``R:`` on Windows or
            ``/Volumes/NPHome`` on macOS.
        rel_path: Path relative to the destination root.

    Returns:
        str: Absolute path to the directory.
    """
    if destination == 'local':
        home_dir = os.path.expanduser('~')
        path = os.path.join(home_dir, rel_path)
    elif destination == 'server':
        if sys.platform == 'windows':
            network_dir = 'R:'
        elif sys.platform == 'darwin':
            network_dir = '/Volumes/NPHome'
        path = os.path.join(network_dir, rel_path)
    if not os.path.exists(path):
        os.makedirs(path)
    return path


def get_filename(data_dir, basename='data', fformat='.h5'):
    """Return a dated file path inside ``data_dir``, creating directories as needed.

    The path structure is ``data_dir/<year>/<MM. Mon>/<DD>/<basename><fformat>``.

    Args:
        data_dir: Root directory under which to create the dated subdirectory.
        basename: Stem of the filename (default ``'data'``).
        fformat: File extension including the dot (default ``'.h5'``).

    Returns:
        str: Full file path.
    """
    date = datetime.datetime.now()
    output_dir = os.path.join(data_dir, str(date.year),
                              '{:02d}'.format(date.month) + '. ' + date.strftime('%b'),
                              '{:02d}'.format(date.day))
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    file_path = os.path.join(output_dir, basename + fformat)
    return file_path


def get_unique_filename(data_dir, basename='data', fformat='.h5'):
    """Return a unique dated file path, incrementing a counter until the name is free.

    Args:
        data_dir: Root directory under which to create the dated subdirectory.
        basename: Stem of the filename (default ``'data'``).
        fformat: File extension including the dot (default ``'.h5'``).

    Returns:
        str: Full file path that does not yet exist on disk.
    """
    date = datetime.datetime.now()
    output_dir = os.path.join(data_dir, str(date.year),
                              '{:02d}'.format(date.month) + '. ' + date.strftime('%b'),
                              '{:02d}'.format(date.day), basename + 's')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    unique_id = 1
    file_path = os.path.join(output_dir, basename + '_' + str(unique_id) + fformat)
    while os.path.exists(file_path):
        unique_id += 1
        file_path = os.path.join(output_dir, basename + '_' + str(unique_id) + fformat)
    return file_path


def get_file(destination='local',
             rel_path='Desktop/Data',
             basename='data',
             fformat='.h5',
             set_current=True):
    """Open or create a DataFile at a standard dated path and return it.

    Args:
        destination: Passed to :func:`get_data_dir` (``'local'`` or
            ``'server'``).
        rel_path: Relative path within the destination root.
        basename: Stem of the filename (default ``'data'``).
        fformat: File extension including the dot (default ``'.h5'``).
        set_current: If True (default), register the file as the current
            datafile.

    Returns:
        DataFile: The opened file.
    """
    data_dir = get_data_dir(destination, rel_path)
    fname = get_filename(data_dir, basename, fformat)
    f = DataFile(fname)
    if set_current:
        f.make_current()
    return f


def transpose_datafile(data_set):
    """Transpose a dataset in-place, replacing it with its transposed copy.

    Args:
        data_set: The h5py Dataset to transpose. It is deleted and re-created
            under the same name within its parent group.
    """
    parent = data_set.parent
    transposed_datafile = np.copy(data_set[...].T)
    file_name = data_set.name.split('/')[-1]
    del parent[file_name]
    parent.create_dataset(file_name, data=transposed_datafile)


def wrap_h5py_item(item):
    """Wrap an h5py object: groups are returned as Group objects, datasets are unchanged."""
    if isinstance(item, h5py.Group):
        # wrap groups before returning them (this makes our group objects rather than h5py.Group)
        return Group(item.id)
    else:
        return item  # for now, don't bother wrapping datasets


def ensure_str(str_or_bytes):
    """Decode bytes to str, or coerce any other type with ``str()``.

    Args:
        str_or_bytes: Value to convert.

    Returns:
        str: String representation.
    """
    if type(str_or_bytes) in (bytes, np.bytes_):
        return str_or_bytes.decode()
    return str(str_or_bytes)


def sort_by_timestamp(hdf5_group):
    """Return items in an HDF5 group sorted by their ``creation_timestamp`` attribute.

    Falls back to alphabetical ordering by numeric suffix if timestamps are absent.

    Args:
        hdf5_group: An h5py Group (or Group-like mapping) whose values carry a
            ``creation_timestamp`` attribute.

    Returns:
        list[tuple[str, h5py.Group | h5py.Dataset]]: ``(key, item)`` pairs in
        chronological order.
    """
    keys = list(hdf5_group.keys())
    try:
        time_stamps = []
        for value in list(hdf5_group.values()):

            time_stamp_str = ensure_str(value.attrs['creation_timestamp'])
            try:
                time_stamp_float = datetime.datetime.strptime(time_stamp_str,
                                                              "%Y-%m-%dT%H:%M:%S.%f")
            except ValueError:
                time_stamp_str = time_stamp_str + '.0'
                time_stamp_float = datetime.datetime.strptime(time_stamp_str,
                                                              "%Y-%m-%dT%H:%M:%S.%f")
            time_stamps.append(time_stamp_float)
        keys = np.array(keys)[np.argsort(time_stamps)]
    except KeyError:
        keys.sort(key=lambda n: n.split('_')[-1] if '_' in n else n)
    items_lists = [(key, hdf5_group[key]) for key in keys]
    return items_lists


class Group(h5py.Group, ShowGUIMixin):
    """An h5py Group extended for scientific data storage.

    Adds auto-incrementing dataset and group names, creation timestamps,
    metadata attribute helpers, and resizable dataset support. All group
    lookups return ``Group`` instances rather than bare ``h5py.Group`` objects.
    """

    def __getitem__(self, key):
        item = super(Group, self).__getitem__(key)  # get the dataset or group
        return wrap_h5py_item(item)  #wrap as a Group if necessary

    @property
    def parent(self):
        """Return the group to which this object belongs."""
        return wrap_h5py_item(super(Group, self).parent)

    def find_unique_name(self, name):
        """Return a unique name for a new child of this group.

        Args:
            name: Desired name. If it contains ``%d``, that placeholder is
                replaced with the lowest integer that makes the name unique.
                If it does not contain ``%d`` and the name already exists,
                ``_%d`` is appended before applying the same logic.

        Returns:
            str: A name not currently present in this group.
        """
        if "%d" not in name and name not in list(self.keys()):
            return name  # simplest case: it's a unique name
        else:
            n = 0
            if "%d" not in name:
                name += "_%d"
            while (name % n) in self:
                n += 1  # increase the number until the name's unique
            return (name % n)

    def numbered_items(self, name):
        """Return children whose names start with ``name`` followed by a number.

        Results are sorted numerically rather than lexicographically, so
        ``item_10`` comes after ``item_9``.

        Args:
            name: Common name prefix to match (without the trailing number).

        Returns:
            list: Matching groups/datasets in ascending numeric order.
        """
        items = [
            wrap_h5py_item(v)
            for k, v in list(self.items())
            if k.startswith(name)  # only items that start with `name`
            and re.match(r"_*(\d+)$", k[len(name):])]  # and end with numbers
        return sorted(items, key=h5_item_number)

    def count_numbered_items(self, name):
        """Count children whose names start with ``name`` followed by a number.

        Faster than ``len(numbered_items(name))`` as it avoids wrapping items.

        Args:
            name: Common name prefix to match.

        Returns:
            int | None: The count, or None if no matching items exist.
        """
        n = 0
        for k in list(self.keys()):
            if k.startswith(name) and re.match(r"_*(\d+)$", k[len(name):]):
                n += 1
                return n

    def create_group(self, name, attrs=None, auto_increment=True, timestamp=True):
        """Create a subgroup, using auto-incrementing naming to avoid overwrites.

        Args:
            name: Name for the new group. May contain a ``%d`` placeholder as
                accepted by :meth:`find_unique_name`.
            attrs: Optional dict of HDF5 metadata attributes to set on the group.
            auto_increment: If True (default), ensure the name is unique via
                :meth:`find_unique_name`. Set to False to raise an error if the
                name already exists.
            timestamp: If True (default), write a ``creation_timestamp`` attribute.

        Returns:
            Group: The newly created group.
        """
        if auto_increment and name is not None:
            name = self.find_unique_name(name)  #name is None if creating via the dict interface
        g = super(Group, self).create_group(name)
        if timestamp:
            g.attrs.create('creation_timestamp', datetime.datetime.now().isoformat().encode())
        if attrs is not None:
            attributes_from_dict(g, attrs)
        return Group(g.id)  # make sure it's wrapped!

    def require_group(self, name):
        """Return a subgroup, creating it if it does not exist."""
        return Group(super(Group, self).require_group(name).id)  # wrap the returned group

    def create_dataset(self,
                       name,
                       auto_increment=True,
                       shape=None,
                       dtype=None,
                       data=None,
                       attrs=None,
                       timestamp=True,
                       autoflush=True,
                       *args,
                       **kwargs):
        """Create a dataset, using auto-incrementing naming to avoid overwrites.

        If ``data`` is an :class:`~pyopenlab.utils.array_with_attrs.ArrayWithAttrs`
        its ``.attrs`` are merged into the dataset attributes automatically.

        Args:
            name: Name for the new dataset. May contain a ``%d`` placeholder.
            auto_increment: If True (default), ensure the name is unique via
                :meth:`find_unique_name`.
            shape: Dataset shape tuple (only needed when ``data`` is not provided).
            dtype: Data type (only needed when ``data`` is not provided).
            data: Array to store. Determines ``shape`` and ``dtype`` if given.
            attrs: Optional dict of HDF5 metadata attributes.
            timestamp: If True (default), write a ``creation_timestamp`` attribute.
            autoflush: If True (default), flush the file after writing.
            *args: Extra positional arguments forwarded to
                ``h5py.Group.create_dataset``.
            **kwargs: Extra keyword arguments forwarded to
                ``h5py.Group.create_dataset``.

        Returns:
            h5py.Dataset: The newly created dataset.
        """
        if auto_increment and name is not None:  #name is None if we are creating via the dict interface
            name = self.find_unique_name(name)
        dset = super(Group, self).create_dataset(name, shape, dtype, data, *args, **kwargs)
        if timestamp:
            dset.attrs.create('creation_timestamp', datetime.datetime.now().isoformat().encode())
        if hasattr(data, "attrs"):  #if we have an ArrayWithAttrs, use the attrs!
            attributes_from_dict(dset, data.attrs)
        if attrs is not None:
            attributes_from_dict(dset, attrs)  # quickly set the attributes
        if autoflush == True:
            dset.file.flush()
        return dset

    create_dataset.__doc__ += '\n\n' + h5py.Group.create_dataset.__doc__

    def require_dataset(self,
                        name,
                        auto_increment=True,
                        shape=None,
                        dtype=None,
                        data=None,
                        attrs=None,
                        timestamp=True,
                        *args,
                        **kwargs):
        """Return an existing dataset by name, or create it if absent.

        Args:
            name: Dataset name.
            auto_increment: Passed to :meth:`create_dataset` if creating.
            shape: Dataset shape (used when creating).
            dtype: Data type (used when creating).
            data: Array data (used when creating).
            attrs: Metadata attributes (used when creating).
            timestamp: Whether to write a creation timestamp (used when creating).
            *args: Forwarded to :meth:`create_dataset`.
            **kwargs: Forwarded to :meth:`create_dataset`.

        Returns:
            h5py.Dataset: Existing or newly created dataset.
        """
        if name not in self:
            dset = self.create_dataset(name, auto_increment, shape, dtype, data, attrs, timestamp,
                                       *args, **kwargs)
        else:
            dset = self[name]
        return dset

    def create_resizable_dataset(self,
                                 name,
                                 shape=(0,),
                                 maxshape=(None,),
                                 auto_increment=True,
                                 dtype=None,
                                 attrs=None,
                                 timestamp=True,
                                 *args,
                                 **kwargs):
        """Create a resizable dataset that can be extended along its first axis.

        Convenience wrapper around :meth:`create_dataset` with ``chunks=True``
        and a ``maxshape`` that allows unlimited growth along axis 0.

        Args:
            name: Dataset name.
            shape: Initial shape (default ``(0,)``).
            maxshape: Maximum shape (default ``(None,)`` — unlimited on axis 0).
            auto_increment: If True (default), ensure the name is unique.
            dtype: Data type.
            attrs: Optional metadata attributes.
            timestamp: If True (default), write a creation timestamp.
            *args: Forwarded to :meth:`create_dataset`.
            **kwargs: Forwarded to :meth:`create_dataset`.

        Returns:
            h5py.Dataset: The newly created resizable dataset.
        """
        return self.create_dataset(name,
                                   auto_increment,
                                   shape,
                                   dtype,
                                   attrs,
                                   timestamp,
                                   maxshape=maxshape,
                                   chunks=True,
                                   *args,
                                   **kwargs)

    def require_resizable_dataset(self,
                                  name,
                                  shape=(0,),
                                  maxshape=(None,),
                                  auto_increment=True,
                                  dtype=None,
                                  attrs=None,
                                  timestamp=True,
                                  *args,
                                  **kwargs):
        """Create a resizeable dataset, or return the dataset if it exists."""
        if name not in self:
            dset = self.create_resizable_dataset(name, shape, maxshape, auto_increment, dtype,
                                                 attrs, timestamp, *args, **kwargs)
        else:
            dset = self[name]
        return dset

    def update_attrs(self, attribute_dict):
        """Update (create or modify) the attributes of this group."""
        attributes_from_dict(self, attribute_dict)

    def append_dataset(self, name, value, dtype=None):
        """Append the given data to an existing dataset, creating it if it doesn't exist."""
        if name not in self:
            if hasattr(value, 'shape'):
                shape = (0,) + value.shape
                maxshape = (None,) + value.shape
            elif isinstance(value, Sequence):
                shape = (0, len(value))
                maxshape = (None, len(value))  # tuple(None for i in shape)
            else:
                shape = (0,)
                maxshape = (None,)
            dset = self.require_dataset(name,
                                        shape=shape,
                                        dtype=dtype,
                                        maxshape=maxshape,
                                        chunks=True)
        else:
            dset = self[name]
        index = dset.shape[0]
        dset.resize(index + 1, 0)
        dset[index, ...] = value

    def get_qt_ui(self):
        """Return a file browser widget for this group."""
        # Sorry about the dynamic import - the alternative is always
        # requiring Qt to access data files, and I think that's worse.
        from pyopenlab.ui.hdf5_browser import HDF5Browser
        return HDF5Browser(self)

    @property
    def basename(self):
        """Return the last part of self.name, i.e. just the final component of the path."""
        return self.name.rsplit("/", 1)[-1]

    def timestamp_sorted_items(self):
        """Return items in this group sorted by their creation timestamp.

        Returns:
            list[tuple[str, h5py.Group | h5py.Dataset]]: ``(key, item)`` pairs
            in chronological order.
        """
        return sort_by_timestamp(self)


class DataFile(Group):
    """An HDF5 file represented as its root Group.

    Inherits all :class:`Group` functionality (auto-incrementing names,
    metadata helpers, etc.) and adds file-level operations: open/close,
    "current file" registration, and optional version-info recording.
    """

    def __init__(self,
                 name,
                 mode='a',
                 save_version_info=False,
                 update_current_group=True,
                 *args,
                 **kwargs):
        """Open or create an HDF5 file.

        Args:
            name: File path, or an already-open ``h5py.Group`` / ``h5py.File``
                to wrap directly.
            mode: HDF5 open mode — ``'r'`` (read-only), ``'r+'`` (read/write,
                must exist), ``'w'`` (create, truncate if exists), ``'w-'``
                (create, fail if exists), ``'a'`` (read/write or create;
                default).
            save_version_info: If True, record a version-info string as a
                top-level attribute on the file.
            update_current_group: Stored on the instance; not used internally
                by DataFile itself.
            *args: Extra positional arguments forwarded to ``h5py.File``.
            **kwargs: Extra keyword arguments forwarded to ``h5py.File``.
        """
        if isinstance(name, h5py.Group):
            f = name  #if it's already an open file, just use it
        else:
            f = h5py.File(name, mode, *args, **kwargs)  # open the file
            try:
                f = h5py.File(name, mode, *args, **kwargs)
            except OSError as e:
                print("problem opening file", e)
                if os.path.getsize(name) < 100 and mode == 'a':  #1kB/10
                    os.remove(name)  # dirty hack to work around mode=a not working
                    # if the file is empty
                else:
                    raise e
                f = h5py.File(name, mode, *args, **kwargs)

        super(DataFile, self).__init__(
            f.id
        )  # initialise a Group object with the root group of the file (saves re-wrapping all the functions for File)
        if save_version_info and self.file.mode != 'r':
            #Save version information if needed
            n = 0
            while "version_info_%04d" % n in self.attrs:
                n += 1
            try:
                self.attrs.create("version_info_%04d" % n,
                                  np.string_(pyopenlab.utils.version.version_info_string()))
            except:
                print("Error: could not save version information")
        self.update_current_group = update_current_group

    def flush(self):
        """Flush pending writes to disk."""
        self.file.flush()

    def close(self):
        """Close the underlying HDF5 file."""
        self.file.close()

    def make_current(self):
        """Set this as the default location for all new data."""
        global _current_datafile
        _current_datafile = self

    @property
    def filename(self):
        """ Returns the filename (full path) of the current datafile """
        return self.file.filename

    @property
    def dirname(self):
        """ Returns the path of the datafolder the current datafile is in"""
        return os.path.dirname(self.file.filename)


_current_datafile = None


def current(create_if_none=True, create_if_closed=True, mode='a', working_directory=None):
    """Return the current datafile, creating one via a Qt dialog if necessary.

    Args:
        create_if_none: If True (default), prompt the user when no current
            file exists.
        create_if_closed: If True (default), treat a closed file as absent
            and prompt for a new one.
        mode: HDF5 open mode for the new file (default ``'a'``).
        working_directory: Directory shown in the file dialog (defaults to
            ``os.getcwd()``).

    Returns:
        DataFile: The current datafile.

    Raises:
        IOError: If no current file exists and one could not be created.
    """
    # TODO: if file previously used but closed don't ask to recreate but use config to open
    global _current_datafile
    if create_if_closed:  # try to access the file - if it's closed, it will fail
        try:
            list(_current_datafile.keys())
        except:  # if the file is closed, set it to none so we make a new one.
            _current_datafile = None

    if _current_datafile is None and create_if_none:
        print("No current data file, attempting to create...")
        if working_directory == None:
            working_directory = os.getcwd()
        try:  # we try to pop up a Qt file dialog
            import pyopenlab.utils.gui
            from pyopenlab.utils.gui import QtGui
            from pyopenlab.utils.gui import QtWidgets
            app = pyopenlab.utils.gui.get_qt_app()  # ensure Qt is running
            fname = QtWidgets.QFileDialog.getSaveFileName(
                caption="Select Data File",
                directory=os.path.join(working_directory,
                                       datetime.date.today().strftime("%Y-%m-%d.h5")),
                filter="HDF5 Data (*.h5 *.hdf5)",
                options=QtWidgets.QFileDialog.DontConfirmOverwrite,
            )
            if not isinstance(fname, str):
                fname = fname[0]  # work around version-dependent Qt behaviour :(
            if len(fname) > 0:
                print(fname)
                if not "." in fname:
                    fname += ".h5"
                set_current(fname, mode=mode)
            #                if os.path.isfile(fname): #FIXME: dirty hack to work around mode=a not working
            #                    set_current(fname,mode='r+')
            #                else:
            #                    set_current(fname,mode='w-') #create the datafile
            else:
                print("Cancelled by the user.")
        except Exception as e:
            print("File dialog went wrong :(")
            print(e)

    if _current_datafile is not None:
        return _current_datafile  # if there is a file (or we created one) return it
    else:
        raise IOError("Sorry, there is no current file to return.")


def set_current(datafile, **kwargs):
    """Set the module-level current datafile.

    Args:
        datafile: A :class:`DataFile`, an ``h5py.Group``, or a file path string.
        **kwargs: Extra keyword arguments forwarded to :class:`DataFile` when
            opening from a path.

    Returns:
        DataFile: The newly registered current datafile.
    """
    global _current_datafile
    if isinstance(datafile, DataFile):
        _current_datafile = datafile
        return _current_datafile
    elif isinstance(datafile, h5py.Group):
        _current_datafile = DataFile(datafile)
        return _current_datafile
    else:
        print("opening file: ", datafile)
        _current_datafile = DataFile(datafile, **kwargs)  # open a new datafile
        return _current_datafile


def set_temporary_current_datafile():
    """Create an in-memory HDF5 file and register it as the current datafile.

    Intended for testing. Data is not persisted to disk.

    Returns:
        DataFile: The temporary in-memory datafile.
    """
    pyopenlab.log("WARNING: using a temporary file")
    print("WARNING: using a file in memory as the current datafile.  DATA WILL NOT BE SAVED.")
    df = h5py.File("temporary_file.h5", driver='core', backing_store=False)
    return set_current(df)


def close_current():
    """Close the current datafile"""
    if _current_datafile is not None:
        try:
            _current_datafile.close()
        except:
            print("Error closing the data file")


_current_group = None
_use_current_group = False


def set_current_group(selected_object):
    """Set the module-level current group used by instruments for data routing.

    If ``selected_object`` is a dataset, its parent group is used. Falls back
    to the root of the current datafile if the object has no parent.

    Args:
        selected_object: A :class:`Group`, ``h5py.Group``, dataset, or
            :class:`~pyopenlab.utils.array_with_attrs.DummyHDF5Group` from
            which the target group is extracted.
    """
    global _current_group
    try:
        if type(selected_object) == DummyHDF5Group:
            potential_group = list(selected_object.values())[0]
        else:
            potential_group = selected_object
        if type(selected_object) == Group or type(selected_object) == h5py.Group:
            _current_group = wrap_h5py_item(selected_object)
        else:
            _current_group = wrap_h5py_item(potential_group.parent)
    except AttributeError:
        _current_group = current()


def open_file(set_current_bool=True, mode='a'):
    """Open an existing HDF5 file via a Qt file dialog.

    Args:
        set_current_bool: If True (default), register the opened file as the
            current datafile.
        mode: HDF5 open mode (default ``'a'``).

    Returns:
        DataFile | None: The opened file, or the existing current datafile if
        the dialog was cancelled.
    """
    global _current_datafile
    try:  # we try to pop up a Qt file dialog
        import pyopenlab.utils.gui
        from pyopenlab.utils.gui import QtGui
        from pyopenlab.utils.gui import QtWidgets
        app = pyopenlab.utils.gui.get_qt_app()  # ensure Qt is running
        fname = QtWidgets.QFileDialog.getOpenFileName(
            caption="Select Existing Data File",
            directory=os.path.join(os.getcwd()),
            filter="HDF5 Data (*.h5 *.hdf5)",
            #            options=qtgui.QFileDialog.DontConfirmOverwrite,
        )
        if not isinstance(fname, str):
            fname = fname[0]  # work around version-dependent Qt behaviour :(
        if len(fname) > 0:
            print(fname)
            if set_current_bool == True:
                set_current(fname, mode=mode)
            else:
                return DataFile(fname, mode=mode)
        else:
            print("Cancelled by the user.")
    except Exception as e:
        print("File dialog went wrong :(")
        print(e)

    return _current_datafile  # if there is a file return it


def create_file(set_current_bool=False, mode='a'):
    """Create a new HDF5 file via a Qt file dialog.

    Args:
        set_current_bool: If True, register the new file as the current
            datafile (default False).
        mode: HDF5 open mode (default ``'a'``).

    Returns:
        DataFile | None: The created file, or the existing current datafile if
        the dialog was cancelled.
    """
    global _current_datafile
    try:  # we try to pop up a Qt file dialog
        import pyopenlab.utils.gui
        from pyopenlab.utils.gui import QtGui
        from pyopenlab.utils.gui import QtWidgets
        app = pyopenlab.utils.gui.get_qt_app()  # ensure Qt is running
        fname = QtWidgets.QFileDialog.getSaveFileName(
            caption="Select Existing Data File",
            directory=os.path.join(os.getcwd()),
            filter="HDF5 Data (*.h5 *.hdf5)",
            #            options=qtgui.QFileDialog.DontConfirmOverwrite,
        )
        if not isinstance(fname, str):
            fname = fname[0]  # work around version-dependent Qt behaviour :(
        if len(fname) > 0:
            print(fname)
            if set_current_bool == True:
                set_current(fname, mode=mode)
            else:
                return DataFile(fname, mode=mode)
        else:
            print("Cancelled by the user.")
    except Exception as e:
        print("File dialog went wrong :(")
        print(e)

    return _current_datafile  # if there is a file return it


if __name__ == '__main__':
    help(Group.create_dataset)
