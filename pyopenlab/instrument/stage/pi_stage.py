"""VISA driver for Physik Instrumente (PI) translation stages."""
from functools import partial
import time

import numpy as np

from pyopenlab.instrument.stage import Stage
from pyopenlab.instrument.stage import StageUI
from pyopenlab.instrument.visa_instrument import VisaInstrument


class PIStage(VisaInstrument, Stage):
    """Control interface for PI stages."""

    def __init__(self, address='ASRL8::INSTR', timeout=10, baud_rate=57600):
        """Open the VISA connection, configure serial settings, and start up.

        Args:
            address (str): VISA resource address of the controller.
            timeout (int): VISA timeout (currently unused; left for API
                compatibility).
            baud_rate (int): Serial baud rate (currently unused; the rate is
                hard-coded to 57600 below).
        """
        super(PIStage, self).__init__(address=address)
        self.instr.read_termination = '\n'
        self.instr.write_termination = '\n'
        self.instr.baud_rate = 57600
        #     self.instr.timeout = 10
        self.axis_names = ('a', 'b')
        self.positions = [0 for ch in range(3)]
        self._stage_id = None
        self.startup()

    def move(self, pos, axis=None, relative=False):
        """Move one or more axes to a position.

        Args:
            pos: Target position(s) in metres, dispatched per axis by
                ``set_axis_param``.
            axis: Axis or axes to move; if None, all axes are addressed.
            relative (bool): If True, move relative to the current position.
        """
        if relative:
            self.set_axis_param(partial(self.move_axis, relative=True), pos, axis)
        else:
            self.set_axis_param(self.move_axis, pos, axis)

    def move_axis(self, pos, axis, relative=False):
        """Move a single axis, then block until it stops.

        Args:
            pos (float): Target position in metres (converted to um for the
                controller).
            axis (str): The axis label.
            relative (bool): If True, move relative to the current position.
        """
        if relative:
            self.write('mvr {0}{1}'.format(axis, 1e6 * pos))
        else:
            self.write('mov {0}{1}'.format(axis, 1e6 * pos))
        self.wait_until_stopped(axis)

    def get_position(self, axis=None):
        """Query the current position of one or all axes.

        Args:
            axis: Axis or axes to query; if None, all axes are returned.

        Returns:
            The position(s) in metres.
        """
        return self.get_axis_param(lambda axis: 1e-6 * float(self.query('pos? {0}'.format(axis))),
                                   axis)

    position = property(fget=get_position, doc="Current position of the stage")

    def is_moving(self, axes=None):
        """Check whether any of the specified axes are in motion.

        The position is polled 3 times to see whether the stage stays close to
        its initial position.

        Args:
            axes: The axes to check.

        Returns:
            bool: True if any axis has moved beyond the threshold.
        """
        positions = np.zeros((3, len(axes)))
        for i in range(3):
            positions[i] = [self.get_position(axis) for axis in axes]
            time.sleep(0.005)
        sum_of_diffs = np.sum(positions - positions[0], axis=1)
        if np.any(sum_of_diffs > 0.01):
            print(sum_of_diffs)
            return True
        else:
            return False

    def wait_until_stopped(self, axes=None):
        """Block until the given axes are no longer moving.

        Args:
            axes: The axes to wait on.
        """
        while self.is_moving(axes=axes):
            time.sleep(0.01)

    def startup(self):
        """Bring the controller online and apply default operating settings."""
        self.online = 1
        while not self.online:
            print(self.online)
        self.loop_mode = 1
        self.speed_mode = 0
        self.velocity = 100
        self.drift_compensation = 0
        self.instr.write('cto 132')
        self.instr.write('cto 232')
        self.instr.write('cto 332')

    def shutdown(self):
        """Disable closed-loop control and take the controller offline."""
        self.loop_mode = 0
        self.online = 0

    def get_velocity(self, axis=None):
        """Query the closed-loop velocity of one or all axes.

        Args:
            axis: Axis or axes to query; if None, all axes are returned.

        Returns:
            The velocity value(s).
        """
        return self.get_axis_param(lambda axis: float(self.query('vel? {0}'.format(axis))), axis)

    def set_velocity(self, value, axis=None):
        """Set the closed-loop velocity of one or all axes.

        Args:
            value: Velocity to set.
            axis: Axis or axes to set; if None, all axes are addressed.
        """
        self.set_axis_param(lambda value, axis: self.write('vel {0}{1}'.format(axis, value)), value,
                            axis)

    velocity = property(get_velocity, set_velocity)

    def get_drift_compensation(self, axis=None):
        """Query the drift-compensation state of one or all axes.

        Args:
            axis: Axis or axes to query; if None, all axes are returned.

        Returns:
            The drift-compensation flag(s).
        """
        return self.get_axis_param(lambda axis: bool(self.query('dco? {0}'.format(axis))), axis)

    def set_drift_compensation(self, value, axis=None):
        """Set the drift-compensation state of one or all axes.

        Args:
            value: Drift-compensation flag to set.
            axis: Axis or axes to set; if None, all axes are addressed.
        """
        self.set_axis_param(lambda value, axis: self.write('dco {0}{1}'.format(axis, value)), value,
                            axis)

    drift_compensation = property(get_drift_compensation, set_drift_compensation)

    def get_loop_mode(self, axis=None):
        """Query the servo (control loop) mode of one or all axes.

        Args:
            axis: Axis or axes to query; if None, all axes are returned.

        Returns:
            The loop-mode flag(s).
        """
        return self.get_axis_param(lambda axis: bool(self.query('svo? {0}'.format(axis))), axis)

    def set_loop_mode(self, value, axis=None):
        """Set the servo (control loop) mode of each axis.

        Args:
            value: Servo control mode - 1 for closed loop, 0 for open loop.
            axis: Axis or axes to set; if None, all axes are addressed.
        """
        self.set_axis_param(lambda value, axis: self.write('svo {0}{1}'.format(axis, value)), value,
                            axis)

    loop_mode = property(get_loop_mode, set_loop_mode)

    def get_speed_mode(self, axis=None):
        """Query the speed-control mode of one or all axes.

        Args:
            axis: Axis or axes to query; if None, all axes are returned.

        Returns:
            The speed-mode flag(s).
        """
        return self.get_axis_param(lambda axis: bool(self.query('vco? {0}'.format(axis))), axis)

    def set_speed_mode(self, value, axis=None):
        """Set the speed-control mode of each axis.

        Args:
            value: Speed control mode - 1 for controlled speed, 0 for fastest.
            axis: Axis or axes to set; if None, all axes are addressed.
        """
        self.set_axis_param(lambda value, axis: self.write('vco {0}{1}'.format(axis, value)), value,
                            axis)

    speed_mode = property(get_speed_mode, set_speed_mode)

    def get_online(self):
        """Return whether the controller is online.

        Returns:
            bool: True if the controller reports online.
        """
        return bool(self.query('onl?'))

    def set_online(self, value):
        """Set the controller online/offline state.

        Args:
            value: 1 for online, 0 for offline.
        """
        self.write('onl {0}'.format(value))

    online = property(get_online, set_online)

    def get_on_target(self):
        """Return whether the stage has reached its target position.

        Returns:
            bool: True if on target.
        """
        return bool(self.query('ont?'))

    on_target = property(get_on_target)

    def get_id(self):
        """Return the controller identification string (cached after first read).

        Returns:
            str: The ``*idn?`` response.
        """
        if self._stage_id is None:
            self._stage_id = self.query('*idn?')
        return self._stage_id

    stage_id = property(get_id)

    def get_qt_ui(self):
        """Create the Qt control UI for this stage.

        Returns:
            StageUI: A Qt widget for interactive control.
        """
        return StageUI(self, stage_step_min=0.1e-9, stage_step_max=100e-6)


if __name__ == '__main__':
    stage = PIStage(address='ASRL4::INSTR')
#  stage.move((5e-6, 10e-6))
#    print stage.position
#    print stage.get_position()
#    print stage.get_position(axis=('a', 'b'))
#
#    import sys
#    from pyopenlab.utils.gui import get_qt_app
#    app = get_qt_app()
#    ui = stage.get_qt_ui()
#    ui.show()
#    sys.exit(app.exec_())
