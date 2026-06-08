# -*- coding: utf-8 -*-
"""Camera subclass with scaled, unit-aware axes and crosshair-based ROI selection.

The GUI provides crosshairs for defining regions of interest, and the display widget keeps the
scaled axes and ROI selection consistent regardless of the camera's binning.
"""

from weakref import WeakSet

import numpy as np
import pyqtgraph
from pyqtgraph.graphicsItems.GradientEditorItem import Gradients

from pyopenlab.instrument.camera import Camera
from pyopenlab.ui.widgets.imageview import ExtendedImageView
from pyopenlab.utils.array_with_attrs import ArrayWithAttrs
from pyopenlab.utils.gui import QtCore
from pyopenlab.utils.gui import QtGui
from pyopenlab.utils.gui import QtWidgets


class CameraRoiScale(Camera):
    """Camera with scaled, unit-aware axes and crosshair-based ROI selection.

    The class provides two main features:

    - Scaled axes with whatever units the user wants. Subclasses may provide an array (``x_axis``
      or ``y_axis``) as a lookup table.
    - ROI selection using crosshairs. Subclasses should overwrite the ``roi`` property, e.g. to set
      the ROI in the camera hardware.

    Binning is handled here too: the scaled axes and ROI selection are kept unaffected by binning.

    Args:
        crosshair_origin: Corner the crosshair coordinates are measured from. One of
            ``'top_left'``, ``'top_right'``, ``'bottom_left'`` or ``'bottom_right'``.
    """

    def __init__(self, crosshair_origin='top_left'):
        super(CameraRoiScale, self).__init__()
        self.axis_values = dict(bottom=None, left=None, top=None, right=None)
        self.axis_units = dict(bottom=None, left=None, top=None, right=None)
        self._roi = (0, 1000, 0, 1000)
        self.detector_shape = (1000, 1000)
        self.crosshair_origin = crosshair_origin

    @property
    def x_axis(self):
        return self.axis_values['bottom']

    @x_axis.setter
    def x_axis(self, value):
        self.axis_values['bottom'] = value

    @property
    def y_axis(self):
        return self.axis_values['left']

    @y_axis.setter
    def y_axis(self, value):
        self.axis_values['left'] = value

    @property
    def roi(self):
        """The current region of interest.

        If the camera supports setting a ROI in hardware, subclasses should overwrite this property.

        Returns:
            tuple[int, int, int, int]: Pixel positions ``(xmin, xmax, ymin, ymax)``.
        """
        return self._roi

    @roi.setter
    def roi(self, value):
        """Set the region of interest.

        By default this installs a ``filter_function`` that crops each frame down to the given ROI.

        Args:
            value: 4-tuple of integers, the pixel positions ``(xmin, xmax, ymin, ymax)``.
        """
        self._roi = value

        def fltr(img):
            return img[self._roi[2]:self._roi[3], self._roi[0]:self._roi[1]]

        setattr(self, 'filter_function', fltr)

    @property
    def gui_roi(self):
        """The ROI defined by the crosshairs in the preview widget.

        Returns:
            tuple[int, int, int, int]: The x, y positions of the two crosshairs in the preview
            widget. Defaults to ``(0, 1, 0, 1)`` if no ROI has been drawn.
        """
        assert len(self._preview_widgets) == 1
        for wdg in self._preview_widgets:
            lims = wdg.get_roi()
            if lims is None:
                lims = (0, 1, 0, 1)
        return lims

    @property
    def binning(self):
        """The camera binning, passed to the display widgets to keep scaling and units constant.

        By default the camera is assumed not to support binning, so this returns ``(1, 1)`` and has
        no setter. Subclasses should overwrite this if the camera supports binning.

        Returns:
            tuple[int, int]: The binning factors ``(x, y)``.
        """
        return 1, 1

    def update_widgets(self):
        """Push position, scale, axis values/units and crosshair sizes to the preview widgets."""
        if self._preview_widgets is not None:
            for widgt in self._preview_widgets:
                if isinstance(widgt, DisplayWidgetRoiScale):
                    # Set the position of the updated image
                    roi = self.roi
                    widgt._pxl_offset = (roi[0], roi[2])
                    # Set the scaling
                    widgt._pxl_scale = self.binning
                    # Set the axes values and units
                    widgt.axis_values = self.axis_values
                    widgt.axis_units = self.axis_units
                    widgt.x_axis = self.x_axis
                    widgt.y_axis = self.y_axis
                    if not self.live_view:  # not sure why it doesn't work in live view
                        widgt.update_axes()
                    widgt.crosshair_moved()

                    # Resize the crosshairs, so that they are always 1/40th of the total size of the image, but never
                    # less than 5 pixels
                    size = max(((roi[1] - roi[0]) / 40., (roi[3] - roi[2]) / 40., 5))
                    for idx in [1, 2]:
                        xhair = getattr(widgt, 'CrossHair%d' % idx)
                        xhair._size = size
                        if self.crosshair_origin == 'top_left':
                            xhair._origin = [0, 0]
                        elif self.crosshair_origin == 'top_right':
                            xhair._origin = [self.detector_shape[0], 0]
                        elif self.crosshair_origin == 'bottom_left':
                            xhair._origin = [0, self.detector_shape[1]]
                        elif self.crosshair_origin == 'top_right':
                            xhair._origin = [self.detector_shape[0], self.detector_shape[1]]
                        else:
                            self._logger.info(
                                'Not recognised: crosshair_origin = %s. Needs to be top_left, top_right, '
                                'bottom_left or bottom_right' % self.crosshair_origin)
                        xhair.update()

        super(CameraRoiScale, self).update_widgets()

    def get_preview_widget(self):
        """Create and register a new preview widget for this camera.

        Returns:
            DisplayWidgetRoiScale: The newly created preview widget.
        """
        self._logger.debug('Getting preview widget')
        if self._preview_widgets is None:
            self._preview_widgets = WeakSet()
        new_widget = DisplayWidgetRoiScale()
        self._preview_widgets.add(new_widget)

        return new_widget


class DisplayWidgetRoiScale(ExtendedImageView):
    """Preview widget for :class:`CameraRoiScale`.

    Displays either an image (2D/3D frames) or up to four line plots (1D spectra or stacks of a few
    rows), with scaled, unit-aware axes and a histogram.

    Args:
        scale: Pixel scale ``(x, y)`` applied to displayed images.
        offset: Pixel offset ``(x, y)`` of the displayed image, used to honour the camera ROI.
    """
    _max_num_line_plots = 4
    update_data_signal = QtCore.Signal(np.ndarray)

    def __init__(self, scale=(1, 1), offset=(0, 0)):
        super(DisplayWidgetRoiScale, self).__init__()

        self._pxl_scale = scale
        self._pxl_offset = offset

        self.LineDisplay = self.ui.roiPlot  #creates a PlotWidget instance
        self.LineDisplay.showGrid(x=True, y=True)
        self.ui.splitter.setHandleWidth(10)
        self.getHistogramWidget().gradient.restoreState(list(Gradients.values())[1])
        self.imageItem.setTransform(QtGui.QTransform())
        self.LineDisplay.show()

        self.plot = ()
        for ii in range(self._max_num_line_plots):
            self.plot += (self.LineDisplay.plot(
                pen=pyqtgraph.intColor(ii, self._max_num_line_plots)),)

        self.toggle_displays()

        self.checkbox_autorange = QtWidgets.QCheckBox('Autorange')
        self.tools.gridLayout.addWidget(self.checkbox_autorange, 0, 3, 1, 1)

        self.update_data_signal.connect(self._update_image, type=QtCore.Qt.QueuedConnection)

    @property
    def x_axis(self):
        """Convenience wrapper for integration with spectrometer code"""
        return self.axis_values['bottom']

    @x_axis.setter
    def x_axis(self, value):
        self.axis_values['bottom'] = value

    @property
    def y_axis(self):
        """Convenience wrapper for integration with spectrometer code"""
        return self.axis_values['left']

    @y_axis.setter
    def y_axis(self, value):
        self.axis_values['left'] = value

    def update_axes(self):
        """Apply the stored axis values and unit labels to the widget's GUI axes."""
        gui_axes = self.get_axes()
        for ax, name in zip(gui_axes, ["bottom", "left", "top", "right"]):
            if self.axis_values[name] is not None:
                setattr(ax, 'axis_values', self.axis_values[name])
            if self.axis_units[name] is not None:
                ax.setLabel(self.axis_units[name])

        # This is kept in case subclasses overwrite the x_axis or y_axis properties
        for ax, value in zip(gui_axes[:2], [self.x_axis, self.y_axis]):
            if value is not None:
                setattr(ax, 'axis_values', value)

    def toggle_displays(self, boolean=False):
        """Toggle between an image display and a plot widget for line displays.

        Args:
            boolean: If True, display line plots. If False, display images.
        """
        if boolean:
            self.LineDisplay.show()
            self.LineDisplay.showAxis('left')
            self.LineDisplay.setMouseEnabled(True, True)
            self.ui.splitter.setSizes([0, self.height() - 35, 35])
        else:
            self.ui.splitter.setSizes([self.height() - 35, 0, 35])

    def _update_image(self, newimage):
        """Render a new frame, choosing line plots or an image based on its shape.

        Args:
            newimage: The frame to display. 1D arrays and 2D arrays with fewer rows than
                ``_max_num_line_plots`` are shown as line plots; everything else as an image.
        """
        scale = self._pxl_scale
        offset = self._pxl_offset

        if len(newimage.shape) == 1:
            self.toggle_displays(True)
            self.plot[0].setData(x=self.x_axis, y=newimage)
        elif len(newimage.shape) == 2 and newimage.shape[0] < self._max_num_line_plots:
            self.toggle_displays(True)
            for ii, ydata in enumerate(newimage):
                self.plot[ii].setData(x=self.x_axis, y=ydata)
        else:
            self.toggle_displays(False)
            self.setImage(newimage.astype(float),
                          pos=offset,
                          autoRange=self.checkbox_autorange.isChecked(),
                          scale=scale)

    def update_image(self, newimage):
        """Thread-safely request a display update by emitting the new frame as a Qt signal.

        Args:
            newimage: The frame to display.
        """
        self.update_data_signal.emit(newimage)


class DummyCameraRoiScale(CameraRoiScale):
    """A dummy :class:`CameraRoiScale` that generates random data for testing.

    Args:
        data: The kind of data to generate. One of ``'spectrum'``, ``'color_time'``, ``'time'``,
            ``'image'`` or ``'color'``.
    """

    def __init__(self, data='spectrum'):
        super(DummyCameraRoiScale, self).__init__()
        self.data_type = data

    def raw_snapshot(self, update_latest_frame=True):
        """Generate a random frame of the configured ``data_type``.

        Args:
            update_latest_frame: Unused; accepted for compatibility with the base interface.

        Returns:
            tuple[bool, numpy.ndarray]: ``True`` (success) and the generated frame.

        Raises:
            NotImplementedError: If ``data_type`` is not a recognised value.
        """
        if self.data_type == 'spectrum':
            ran = 100 * ArrayWithAttrs(np.random.random(1600))
        elif self.data_type == 'color_time':
            ran = 100 * np.array([np.random.random((200, 1600, 3)) * x for x in np.arange(1, 11)])
        elif self.data_type == 'time':
            ran = 100 * np.array([np.random.random((200, 1600, 3)) * x for x in np.arange(1, 11)])
        elif self.data_type == 'image':
            ran = 100 * np.random.random((200, 1600))
        elif self.data_type == 'color':
            ran = 100 * np.random.random((200, 1600, 3))
        else:
            raise NotImplementedError
        self._latest_raw_frame = ran
        return True, ran

    @property
    def x_axis(self):
        return np.arange(1600) + 1

    @x_axis.setter
    def x_axis(self, value):
        self.axis_values['bottom'] = value


if __name__ == '__main__':
    import sys

    from pyopenlab.utils.gui import get_qt_app
    app = get_qt_app()

    dcrd = DummyCameraRoiScale()
    dcrd.data_type = 'color_time'
    gui = dcrd.show_gui(blocking=False)
    dcrd.raw_snapshot()
    # dw = gui.preview_widget
    # dw.setImage(np.random.random((200, 1600)))
    sys.exit(app.exec_())
