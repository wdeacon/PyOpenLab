"""Notified properties — lightweight callback-enabled descriptors.

This module extends (actually reimplements) Python's properties so that
they can do extra things when their values changed.  It's a super-lightweight
alternative to Traits.  Note that you must be using a new-style class for this
to work (i.e. you must inherit from object).

`DumbNotifiedProperty` instances work just like regular variables:

>>> class foo(object):
...     a = DumbNotifiedProperty()
>>>
>>> f = foo()
>>> f.a = 4
>>> f.a
4
>>> f.a=5
>>> f.a
5

They can also have default values:

>>> class foo(object):
...     b = DumbNotifiedProperty(10)
>>>
>>> f = foo()
>>> f.b
10

`NotifiedProperty` just extends the usual `property` mechanism:

>>> class foo(object):
...     a = DumbNotifiedProperty()
...     b = DumbNotifiedProperty(10)
...     @NotifiedProperty
...     def c(self):
...         return 99
...     @c.setter
...     def c(self, val):
...         print("discarding {0}".format(val))
>>>
>>> f = foo()
>>> f.c
99
>>> f.c = 10
discarding 10
>>> f.c
99

To register for notification, use register_for_property_changes

>>> def a_changed(a):
...     print("A changed to '{0}'".format(a))
>>> register_for_property_changes(f, "a", a_changed)
>>> f.a=6
A changed to '6'

If you inherit from `NotifiedPropertiesMixin` there will also be a method of
the object called `register_for_property_changes` that doesn't require the
object to be passed in.
        
"""

import functools
from weakref import WeakKeyDictionary

import numpy as np


class Property():
    """Pure-Python reimplementation of the built-in property descriptor.

    Provides the same ``getter``/``setter``/``deleter`` decorator interface as
    the built-in ``property``, serving as the base for :class:`NotifiedProperty`.
    """

    def __init__(self, fget=None, fset=None, fdel=None, doc=None):
        """Create a property descriptor.

        Args:
            fget: Getter function, or None for a write-only property.
            fset: Setter function, or None for a read-only property.
            fdel: Deleter function, or None if deletion is not supported.
            doc: Docstring. Defaults to ``fget.__doc__`` if not provided.
        """
        self.fget = fget
        self.fset = fset
        self.fdel = fdel
        if doc is None and fget is not None:
            doc = fget.__doc__
        self.__doc__ = doc

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        if self.fget is None:
            raise AttributeError("unreadable attribute")
        return self.fget(obj)

    def __set__(self, obj, value):
        if self.fset is None:
            raise AttributeError("can't set attribute")
        self.fset(obj, value)

    def __delete__(self, obj):
        if self.fdel is None:
            raise AttributeError("can't delete attribute")
        self.fdel(obj)

    def getter(self, fget):
        """Return a copy of this property with a new getter function."""
        return type(self)(fget, self.fset, self.fdel, self.__doc__)

    def setter(self, fset):
        """Return a copy of this property with a new setter function."""
        return type(self)(self.fget, fset, self.fdel, self.__doc__)

    def deleter(self, fdel):
        """Return a copy of this property with a new deleter function."""
        return type(self)(self.fget, self.fset, fdel, self.__doc__)


class NotifiedProperty(Property):
    """A property that notifies when it's changed."""

    def __init__(self,
                 fget=None,
                 fset=None,
                 fdel=None,
                 doc=None,
                 read_back=False,
                 single_update=True):
        """Create a property that fires callbacks when its value changes.

        Args:
            fget: Getter function.
            fset: Setter function.
            fdel: Deleter function.
            doc: Docstring.
            read_back: If True, re-read the property immediately after writing
                so callbacks receive the actual stored value rather than the
                requested one. Useful when the setter applies validation or
                rounding. Defaults to False to avoid expensive reads.
            single_update: If True (and ``read_back`` is True), only fire
                callbacks when the value has actually changed.
        """
        super(NotifiedProperty, self).__init__(fget=fget, fset=fset, fdel=fdel, doc=doc)
        # We store a set of callbacks for each object (NB there's one property
        # per *class* not per object, so we have to keep track of instances)
        # This is weakly-referenced so if the objects die, we don't stop
        # Python garbage-collecting them.
        self.callbacks_by_object = WeakKeyDictionary()
        self.read_back = read_back
        self.single_update = single_update
        self.last_value = None

    def __set__(self, obj, value):
        """Update the property's value, and notify listeners of the change."""
        super(NotifiedProperty, self).__set__(obj, value)
        if self.read_back:
            # This ensures the notified value is correct, at the expense of a read
            if self.single_update:
                if value != self.last_value:
                    if len(str(value).split('.')) == 1:
                        self.last_value = self.__get__(obj)
                    else:
                        self.last_value = np.round(self.__get__(obj),
                                                   len(str(value).split('.')[-1]))
                    self.send_notification(obj, self.__get__(obj))

        #
            else:
                self.send_notification(obj, self.__get__(obj))
        else:
            # This is faster, but notifies the requested value, not the actual one
            self.send_notification(obj, value)

    def register_callback(self, obj, callback):
        """Register a function to be called whenever the property changes.

        Args:
            obj: The instance on which to listen for changes.
            callback: Callable accepting one argument — the new value. If it
                raises an exception it will be automatically deregistered.
        """
        if obj not in list(self.callbacks_by_object.keys()):
            self.callbacks_by_object[obj] = set()
        self.callbacks_by_object[obj].add(callback)

    def deregister_callback(self, obj, callback):
        """Remove a previously registered callback.

        Args:
            obj: The instance the callback was registered on.
            callback: The callable to remove.

        Raises:
            KeyError: If no callbacks have been registered on ``obj``.
        """
        try:
            callbacks = self.callbacks_by_object[obj]
        except KeyError:
            raise KeyError("There don't appear to be any callbacks defined on this object!")
        try:
            callbacks.remove(callback)
        except KeyError:
            pass  # Don't worry if callbacks are removed pointlessly!

    def send_notification(self, obj, value):
        """Fire all registered callbacks for ``obj`` with the new value.

        Args:
            obj: The instance whose property changed.
            value: The new value to pass to each callback.
        """
        if obj in self.callbacks_by_object:
            for callback in self.callbacks_by_object[obj].copy():
                try:
                    callback(value)
                except:
                    # Get rid of failed/deleted callbacks
                    # Sometimes Qt objects don't delete cleanly, hence this bodge.
                    self.deregister_callback(obj, callback)


class DumbNotifiedProperty(NotifiedProperty):
    """A property that acts as a plain variable but fires callbacks on change.

    Unlike :class:`NotifiedProperty`, no getter/setter functions are needed —
    the value is stored internally per-instance.
    """

    def __init__(self, default=None, fdel=None, doc=None):
        """Create a self-storing notified property.

        Args:
            default: Default value returned before the property has been set.
            fdel: Optional deleter function.
            doc: Docstring for the property.
        """
        super(DumbNotifiedProperty, self).__init__(fget=self.fget,
                                                   fset=self.fset,
                                                   fdel=fdel,
                                                   doc=doc)
        self._value = default
        self.values_by_object = WeakKeyDictionary()  # we store callbacks here

    def fget(self, obj):
        """Return the stored value for ``obj``, falling back to the default."""
        try:
            # First, try tp return the stored value for that object
            return self.values_by_object[obj]
        except KeyError:
            # Fall back on the default if not.
            return self._value

    def fset(self, obj, value):
        """Store ``value`` for ``obj``."""
        self.values_by_object[obj] = value


def register_for_property_changes(obj, property_name, callback):
    """Register a callback to be called when a named property changes.

    Args:
        obj: The instance to watch.
        property_name: Name of the :class:`NotifiedProperty` to watch.
        callback: Callable accepting one argument — the new value. Note this
            is the value passed to the setter; if the setter applies logic,
            retrieve the property inside the callback to get the actual result.

    Raises:
        AssertionError: If ``property_name`` is not a :class:`NotifiedProperty`
            on ``obj``'s class.
    """
    prop = getattr(obj.__class__, property_name, None)
    assert isinstance(prop, NotifiedProperty), "The specified property isn't available"

    # register the callback.  Note we need to pass the current object in so
    # the property knows which object we're talking about.
    prop.register_callback(obj, callback)


class NotifiedPropertiesMixin(object):
    """A mixin class that adds support for notified properties.
    
    Notified proprties are a very, very lightweight alternative to Traits.
    They don't (currently) do any data validation, though nothing in principle
    stops you extending them to do that.  Essentially, you decorate the setter
    of a property with @add_notification, and add this mixin to the class.
    
    It's then possible to register to find out whenever that property changes.
    """

    @functools.wraps(register_for_property_changes)
    def register_for_property_changes(self, property_name, callback):
        return register_for_property_changes(self, property_name, callback)


if __name__ == '__main__':
    import doctest
    doctest.testmod()

    class foo():
        a = DumbNotifiedProperty(10)

    f = foo()
    f.a = 11

    def a_changed(new):
        print('a changed to ' + str(new))

    register_for_property_changes(f, 'a', a_changed)
    f.a = 12
