"""Unit support for pyopenlab.

Utility functions for attaching, reading, and converting physical units on
array data. Units are stored as pint Quantities or as a ``'units'`` string in
an :class:`~pyopenlab.utils.array_with_attrs.ArrayWithAttrs` attrs dict, making
them compatible with HDF5 metadata.

Translation stages and other instruments can be very sensitive to unit errors
(e.g. being commanded 1000 nm when 1 µm was intended), so attaching units to
measured and commanded values is strongly recommended.
"""
import pint

from pyopenlab import ArrayWithAttrs
from pyopenlab.utils.array_with_attrs import ensure_attrs

ureg = pint.UnitRegistry()  #this should always be where the unit registry comes from


def get_unit_string(obj, default=None, warn=False, fail=False):
    """Return a string representation of an object's units, suitable for HDF5 storage.

    Checks ``obj.attrs['units']`` first (for :class:`ArrayWithAttrs`), then
    falls back to ``str(obj.units)`` (for pint Quantities).

    Args:
        obj: Object to inspect — either an :class:`ArrayWithAttrs` with a
            ``'units'`` entry in its attrs dict, or a pint Quantity.
        default: Value to return if no units are found and ``fail`` is False.
            Defaults to None.
        warn: If True, print a warning when no units are found.
        fail: If True, raise a ValueError when no units are found instead of
            returning ``default``.

    Returns:
        str | default: The unit string, or ``default`` if not found.

    Raises:
        ValueError: If ``fail`` is True and no units are found.
    """
    try:
        return obj.attrs.get('units')  #this works for things with attrs
    except AttributeError:
        try:
            return str(obj.units)  #this works for Quantities
        except Exception:
            if warn:
                print("Warning: no unit string found on " + str(obj))
            if fail:
                raise ValueError("No unit information was found on " + str(obj))
            return default


def unit_to_string(quantity):
    """Convert a pint Quantity to a string, omitting the magnitude when it is unity.

    Args:
        quantity: A pint Quantity to convert.

    Returns:
        str: ``str(quantity.units)`` if the magnitude is 1, otherwise
        ``str(quantity)``.
    """
    if quantity.magnitude == 1:
        return str(quantity.units)
    else:
        return str(quantity)


def get_units(obj, default=None, warn=False):
    """Return the units from an object as a pint Quantity with magnitude one.

    Accepts either an :class:`ArrayWithAttrs` (units stored as a string in
    ``obj.attrs['units']``) or a pint Quantity. Arrays may carry a non-unity
    magnitude in their unit string (e.g. ``"100 nm"`` for camera pixels), in
    which case the returned Quantity preserves that magnitude.

    Args:
        obj: Object to inspect — an :class:`ArrayWithAttrs` or pint Quantity.
        default: Fallback unit to return if no units are found. Passed through
            :func:`ensure_unit`. Defaults to None.
        warn: If True, print a warning when falling back to ``default``.

    Returns:
        pint.Quantity: The units of ``obj``, or the ``default`` unit.

    Raises:
        ValueError: If no units are found and ``default`` is None.
    """
    try:
        if isinstance(obj, ureg.Quantity):
            return ureg.Quantity(1, obj.units)  #if we have a Quantity, return its units
        else:
            unit_string = get_unit_string(obj, fail=True)  #look for a units attribute
            return ureg(unit_string)  #convert to a pint unit
    except Exception:
        if warn:
            print("Warning: no units found on " + str(obj))
        if default is not None:
            return ensure_unit(default)
        else:
            raise ValueError(
                "No unit information could be found on " + str(obj) +
                " (it should either have an attrs dict with a 'units' attribute, or be a Quantity)."
            )


def array_with_units(obj, units):
    """Return an :class:`ArrayWithAttrs` with a ``'units'`` metadata entry.

    Args:
        obj: Array-like to wrap.
        units: Units to attach — any value accepted by :func:`ensure_unit`,
            including strings (``'nm'``, ``'mm/s'``) and pint Quantities.

    Returns:
        ArrayWithAttrs: The input wrapped with ``attrs['units']`` set.
    """
    ret = ensure_attrs(obj)
    ret.attrs.create('units', str(units))
    return ret


def ensure_unit(obj):
    """Coerce an object to a pint Quantity.

    Args:
        obj: A pint Quantity, UnitsContainer, or string representation of a
            unit (e.g. ``'nm'``, ``'mm/s'``).

    Returns:
        pint.Quantity: The input unchanged if already a Quantity, otherwise
        parsed from its string representation.
    """
    if isinstance(obj, ureg.Quantity):
        return obj  #if it's a quantity, we're good.
    else:
        return ureg(str(obj))  #otherwise, convert to string and parse


def convert_quantity(obj, dest_units, default=None, warn=True, return_quantity=False):
    """Convert an array or Quantity to the requested units.

    If the object's units already match ``dest_units`` it is returned unchanged.

    Args:
        obj: An :class:`ArrayWithAttrs` with a ``'units'`` entry, or a pint
            Quantity.
        dest_units: Target units — any value accepted by :func:`ensure_unit`.
        default: Fallback source units if ``obj`` carries no unit information.
            Defaults to None.
        warn: If True, warn when falling back to ``default`` source units.
            Defaults to True.
        return_quantity: If True, return a pint Quantity; if False (default),
            return the bare magnitude array.

    Returns:
        numpy.ndarray | pint.Quantity: The converted data. A bare array is
        returned by default; pass ``return_quantity=True`` for a Quantity.
    """
    if ensure_unit(dest_units) == get_units(obj, default=default, warn=False):
        return obj  #make sure objects are returned unchanged if units match
    if isinstance(obj, ureg.Quantity):
        q = obj
    else:
        fu = get_units(obj, default=default, warn=warn)
        q = ureg.Quantity(obj, fu.units) / fu.magnitude
    du = ensure_unit(dest_units)
    rq = q.to(du.units) / du.magnitude
    if return_quantity:
        return rq
    else:
        return rq.magnitude  #this should return an array/whatever
