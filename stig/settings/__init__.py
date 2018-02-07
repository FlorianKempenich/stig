# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details
# http://www.gnu.org/licenses/gpl-3.0.txt

from .defaults import init_defaults

from blinker import Signal
from collections import abc


class Settings(abc.Mapping):
    """Specialized mapping for *Value instances"""

    def __init__(self, *values):
        # _values and _values_dict hold the same instances; the list is to
        # preserve order and the dict is for fast access via __getitem__
        self._values = []
        self._values_dict = {}
        self._on_change = Signal()
        self.load(*values)
        self._callback = (None, None)

    def add(self, value):
        """Add `value` to collection"""
        self._values.append(value)
        self._values_dict[value.name] = value
        callback, autoremove = self._callback
        if callback is not None:
            setting._on_change.connect(callback, weak=autoremove)

    def load(self, *values):
        """Add multiple `values` to collection"""
        for v in values:
            self.add(v)

    def rename(self, old, new):
        """Change setting's name from `old` to `new`"""
        setting = self[old]
        setting.name = new
        self._values_dict[new] = setting
        del self._values_dict[old]

    @property
    def values(self):
        """Iterate over collected values"""
        yield from self._values

    @property
    def names(self):
        """Iterate over values' `name` properties"""
        yield from self._values_dict.keys()

    def on_change(self, callback, autoremove=True):
        """
        Run `callback` every time a value changes

        `callback` gets the value instances as the only argument.

        If `autoremove` is True, stop calling `callback` once it is garbage
        collected.
        """
        self._callback = (callback, autoremove)
        for setting in self._values:
            setting._on_change.connect(callback, weak=autoremove)

    def __getitem__(self, name):
        return self._values_dict[name]

    def __contains__(self, name):
        return name in self._values_dict

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)
