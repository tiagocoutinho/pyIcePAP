import time
import collections.abc
from typing import Union, Sequence

from .axis import IcePAPAxis


class Group:

    def __init__(self, motors):
        ctrls = set(motor._ctrl for motor in motors)
        assert len(ctrls) == 1, 'motors must be from same controller'
        self._controller = ctrls.pop()
        self._motors = motors

    @property
    def controller(self):
        return self._controller

    @property
    def motors(self):
        return self._motors

    @property
    def axes(self):
        return [motor.axis for motor in self._motors]

    def get_names(self):
        return [motor.name for motor in self._motors]

    def get_acctime(self):
        return self._controller.get_acctime(self.axes)

    def get_velocity(self):
        return self._controller.get_velocity(self.axes)

    def get_pos(self):
        return self._controller.get_pos(self.axes)

    def get_fpos(self):
        return self._controller.get_fpos(self.axes)

    def get_states(self):
        return self._controller.get_states(self.axes)

    def is_moving(self):
        return any(state.is_moving() for state in self.get_states())

    def get_power(self):
        return self._controller.get_power(self.axes)

    def stop(self):
        self._controller.stop(self.axes)

    def start_move(self, positions, **kwargs):
        args = [[mot.addr, pos] for mot, pos in zip(self._motors, positions)]
        self._controller.move(args, **kwargs)

    def wait_stopped(self, timeout=None, interval=10e-3):
        """Helper loop to wait for group to finish moving"""

        start = time.time()
        while self.is_moving():
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
    elif isinstance(obj, collections.abc.Sequence):
        group = Group(obj)
    else:
        raise TypeError('parameter must be Group, Axis or sequence of Axis')
    return group
