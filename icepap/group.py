import time
import collections.abc
from typing import Union, Sequence

from .axis import IcePAPAxis


class Group:

    def __init__(self, motors):
        ctrls = set(motor._ctrl for motor in motors)
        assert len(ctrls) == 1, 'Group motors must be from same controller'
        self.controller = ctrls.pop()
        self.motors = motors
        self._axes = None
        self._names = None

    @property
    def axes(self):
        if self._axes is None:
            self._axes = [motor.axis for motor in self.motors]
        return self._axes

    @property
    def names(self):
        if self._names is None:
            self._names = [motor.name for motor in self.motors]
        return self._names

    @property
    def acctimes(self):
        return self.controller.get_acctime(self.axes)

    @property
    def velocities(self):
        return self.controller.get_velocity(self.axes)

    @property
    def positions(self):
        return self.controller.get_pos(self.axes)

    @property
    def fpositions(self):
        return self.controller.get_fpos(self.axes)

    '''
    @property
    def user_pos(self):
        return [_motor_user_pos(motor, pos)
                for motor, pos in zip(self.motors, self.positions)]

    @property
    def user_fpos(self):
        return [_motor_user_pos(motor, pos)
                for motor, pos in zip(self.motors, self.fpositions)]
    '''

    @property
    def states(self):
        return self.controller.get_states(self.axes)

    @property
    def is_moving(self):
        return any(state.is_moving() for state in self.states)

    @property
    def powers(self):
        return self.controller.get_power(self.axes)

    def stop(self):
        self.controller.stop(self.axes)

    def start_move(self, positions, **kwargs):
        args = [[mot.addr, pos] for mot, pos in zip(self.motors, positions)]
        self.controller.move(args)

    def wait_stopped(self, timeout=None, interval=10e-3):
        """Helper loop to wait for group to finish moving"""

        start = time.time()
        while self.is_moving:
            time.sleep(interval)
            if timeout:
                elapsed = time.time() - start
                if elapsed > timeout:
                    return False
        return True


def group(obj: Union[Group, IcePAPAxis, Sequence]):
    if isinstance(obj, Group):
        group = obj
    elif isinstance(obj, IcePAPAxis):
        group = Group([obj])
        target_positions = [target_positions]
    elif isinstance(obj, collections.abc.Sequence):
        group = Group(obj)
    else:
        raise TypeError('parameter must be Group, Axis or sequence of Axis')
    return group
