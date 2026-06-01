"""
Instrument Class
================

This base class defines the standard behaviour for pyopenlab's instrument
classes, including default locations for saving data, the ability to find
currently-existing instances of a given instrument class, and some GUI helper
functions.

There's also some support mechanisms for metadata creation, and the bundling
of metadata in ArrayWithAttrs objects that include both data and metadata.
"""

from contextlib import contextmanager
import datetime
import inspect
import logging
import os
from weakref import WeakSet

import h5py

import pyopenlab
from pyopenlab.utils.array_with_attrs import ArrayWithAttrs
import pyopenlab.utils.log
from pyopenlab.utils.log import create_logger
from pyopenlab.utils.show_gui_mixin import ShowGUIMixin
from pyopenlab.utils.thread_utils import background_action_decorator
from pyopenlab.utils.thread_utils import locked_action_decorator

LOGGER = create_logger('Instrument')
LOGGER.setLevel('INFO')


class Instrument(ShowGUIMixin):
    """Base class for all instrument-control classes.

    Handles instance tracking, HDF5 data storage, metadata bundling, and
    per-instrument configuration files. Subclass this and set
    ``metadata_property_names`` to the property names that should be
    automatically saved alongside every dataset.
    """
    __instances = None
    metadata_property_names = (
    )  #"Tuple of names of properties that should be automatically saved as HDF5 metadata

    def __init__(self):
        """Create an instrument object."""
        super(Instrument, self).__init__()
        Instrument.instances_set().add(self)  #keep track of instances (should this be in __new__?)
        self._logger = logging.getLogger('Instrument.' +
                                         str(type(self)).split('.')[-1].split('\'')[0])

    @classmethod
    def instances_set(cls):
        """Return the WeakSet that tracks all live Instrument instances."""
        if Instrument.__instances is None:
            Instrument.__instances = WeakSet()
        return Instrument.__instances

    @classmethod
    def get_instances(cls):
        """Return a list of all available instances of this class."""
        return [i for i in Instrument.instances_set() if isinstance(i, cls)]

    @classmethod
    def get_instance(cls, create=True, exceptions=True, *args, **kwargs):
        """Return an existing instance of this class, creating one if needed.

        Args:
            create: If True (default) and no instance exists, instantiate one
                using ``*args`` and ``**kwargs``.
            exceptions: If True (default) and no instance exists and ``create``
                is False, raise ``IndexError`` instead of returning ``None``.
            *args: Passed to the constructor when creating a new instance.
            **kwargs: Passed to the constructor when creating a new instance.

        Returns:
            An instance of this class.

        Raises:
            IndexError: If no instance exists, ``create`` is False, and
                ``exceptions`` is True.
        """
        instances = cls.get_instances()
        if len(instances) > 0:
            return instances[0]
        else:
            if create:
                return cls(*args, **kwargs)
            else:
                if exceptions:
                    raise IndexError("There is no available instance!")
                else:
                    return None

    @classmethod
    def get_root_data_folder(cls):
        """Return the HDF5 group used as the root data folder for this class.

        Returns the current group override if one is set, otherwise opens (or
        creates) a group named after the class in the current datafile.

        Returns:
            pyopenlab.datafile.Group: The root data folder for this instrument.
        """
        if pyopenlab.datafile._use_current_group == True:
            if pyopenlab.datafile._current_group != None:
                return pyopenlab.datafile._current_group
        f = pyopenlab.current_datafile()
        return f.require_group(cls.__name__)

    @classmethod
    def create_data_group(cls, name, *args, **kwargs):
        """Create a uniquely-named HDF5 group to store one reading.

        Args:
            name: Noun describing the reading (e.g. ``"image"``, ``"spectrum"``).
                A ``_%d`` suffix is appended and auto-incremented to keep names
                unique.
            attrs: Optional dict of HDF5 metadata attributes (passed through to
                ``Group.create_group``).
            *args: Extra positional arguments forwarded to ``Group.create_group``.
            **kwargs: Extra keyword arguments forwarded to ``Group.create_group``.

        Returns:
            pyopenlab.datafile.Group: The newly created group.
        """
        if "%d" not in name:
            name = name + '_%d'
        df = cls.get_root_data_folder()
        return df.create_group(name, auto_increment=True, *args, **kwargs)

    @classmethod
    def create_dataset(cls, name, flush=True, *args, **kwargs):
        """Create a uniquely-named HDF5 dataset to store one reading.

        Args:
            name: Noun describing the reading (e.g. ``"image"``, ``"spectrum"``).
                A ``_%d`` suffix is appended and auto-incremented to keep names
                unique.
            flush: If True (default) and ``data`` is provided, flush the file
                immediately so the dataset is written to disk.
            *args: Extra positional arguments forwarded to
                ``Group.create_dataset``.
            **kwargs: Extra keyword arguments forwarded to
                ``Group.create_dataset`` (e.g. ``data``, ``attrs``).

        Returns:
            h5py.Dataset: The newly created dataset.
        """
        if "%d" not in name:  # is this really necessary?
            name = name + '_%d'
        df = cls.get_root_data_folder()
        dset = df.create_dataset(name, *args, **kwargs)
        if 'data' in kwargs and flush:
            dset.file.flush()  #make sure it's in the file if we wrote data
        return dset

    def log(self, message, level='info'):
        """Save a log message to the current datafile.

        Preferred over ``print`` for debug/informational output — messages are
        persisted in the HDF5 file alongside the data.

        Args:
            message: The message string to log.
            level: Logging level string (default ``'info'``). Passed to
                ``pyopenlab.utils.log.log``.
        """
        pyopenlab.utils.log.log(message, from_object=self, level=level)

    def get_metadata(self, property_names=[], include_default_names=True, exclude=None):
        """Return a dict of instrument properties to save alongside data.

        Reads each property named in ``property_names`` and (optionally) in
        ``self.metadata_property_names``, returning their current values.

        Args:
            property_names: Extra property names to include beyond the class
                defaults.
            include_default_names: If True (default), merge ``property_names``
                with ``self.metadata_property_names``. Set to False to use only
                the explicitly supplied names.
            exclude: Property names to omit from the result. Useful for
                suppressing specific entries from the class defaults.

        Returns:
            dict: Mapping of property name → current value.
        """
        # Convert everything to lists to:
        # * ensure we don't modify the arguments (it copies list arguments)
        # * make it all mutable so we can remove items
        # * prevent errors when adding lists and tuples
        keys = list(property_names)
        if include_default_names:
            keys += list(self.metadata_property_names)
        if exclude is not None:
            for p in exclude:
                try:
                    keys.remove(p)
                except ValueError:
                    pass  # Don't worry if we exclude items that are not there!
        return {name: getattr(self, name) for name in keys}

    metadata = property(get_metadata)

    def bundle_metadata(self, data, enable=True, **kwargs):
        """Attach instrument metadata to an array, returning an ArrayWithAttrs.

        Args:
            data: The numpy array to annotate.
            enable: If False, return ``data`` unchanged (handy for toggling
                metadata collection without changing call sites).
            **kwargs: Forwarded to ``get_metadata`` — use ``property_names`` or
                ``exclude`` to customise which properties are included.

        Returns:
            ArrayWithAttrs | np.ndarray: Annotated array when ``enable`` is
            True, otherwise the original ``data`` unchanged.
        """
        if enable:
            return ArrayWithAttrs(data, attrs=self.get_metadata(**kwargs))
        else:
            return data

    def open_config_file(self):
        """Open (or create) the persistent HDF5 config file for this instrument.

        The file is stored next to the instrument's source module and named
        ``<ClassName>_config.h5``. The same file object is returned on
        subsequent calls.

        Returns:
            pyopenlab.datafile.DataFile: The config file, opened in append mode.
        """
        if not hasattr(self, '_config_file'):
            try:
                f = inspect.getfile(self.__class__)  # fails in IPython
            except (TypeError, ValueError):
                f = inspect.getfile(self.__class__.__init__)  # assumes the inst has an init method
            d = os.path.dirname(f)
            self._config_file = pyopenlab.datafile.DataFile(os.path.join(
                d, self.__class__.__name__ + '_config.h5'),
                                                            mode='a')
            self._config_file.attrs['date'] = datetime.datetime.now().strftime("%H:%M %d/%m/%y")
        return self._config_file

    config_file = property(open_config_file)

    def update_config(self, name, data, attrs=None):
        """Write or overwrite a named dataset in this instrument's config file.

        Args:
            name: Dataset name within the config file.
            data: Value to store (anything accepted by ``h5py`` as dataset data).
            attrs: Optional dict of HDF5 metadata attributes to attach to the
                dataset.
        """
        f = self.config_file
        if name in f.keys():
            try:
                del f[name]
            except:
                f[name][...] = data
                f.flush()
        else:
            f.create_dataset(name, data=data, attrs=attrs)

    @contextmanager
    def temporarily_set(self, **kwargs):
        """Context manager that temporarily overrides instrument properties.

        Saves the current values, applies the overrides on entry, and restores
        the originals on exit (even if an exception is raised).

        Args:
            **kwargs: Property name → temporary value pairs.

        Example:
            >>> with camera.temporarily_set(exposure=1, backgrounded=False):
            ...     image = camera.get_image()
        """
        try:
            original_settings = dict()
            for key, value in kwargs.items():
                original_settings[key] = getattr(self, key)
                setattr(self, key, value)
            yield original_settings
        finally:
            for key, value in original_settings.items():
                setattr(self, key, value)
