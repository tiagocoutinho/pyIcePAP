from collections import namedtuple

from .group import group


MotorMotionState = namedtuple(
    "MotorMotionState", "motor name state pos start target"
)


class BaseMotion:

    def __init__(self, obj, sync_stop=True, on_start_stop=None, on_end_stop=None):
        self.group = group(obj)
        self.sync_stop = sync_stop
        self.on_start_stop = on_start_stop or (lambda *args: None)
        self.on_end_stop = on_end_stop or (lambda *args: None)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_value is not None:
            self.stop(exc_type, exc_value, traceback)

    def stop(self, exc_type=None, exc_value=None, traceback=None):
        result = self._start_stop(exc_type, exc_value, traceback)
        self.group.stop()
        if self.sync_stop:
            self.group.wait_stopped()
        self._end_stop()
        return result

    def _start_stop(self, *args):
        try:
            return self.on_start_stop(*args)
        except Exception as err:
            print(err)

    def _end_stop(self, *args):
        try:
            return self.on_end_stop(*args)
        except Exception as err:
            print(err)


class Motion(BaseMotion):

    def __init__(self, obj, target_positions, sync_stop=True,
                 on_start_stop=None, on_end_stop=None):
        super().__init__(obj, sync_stop, on_start_stop, on_end_stop)
        self.target_positions = target_positions
        self.start_positions = pos = self.group.get_pos()
        self.status = self._get_status(pos=pos, start=pos)

    def _get_status(self, states=None, pos=None, start=None):
        args = (
            self.group.motors,
            self.group.names,
            self.group.get_states() if states is None else states,
            self.group.get_pos() if pos is None else pos,
            self.start_positions if start is None else start,
            self.target_positions
        )
        return [MotorMotionState(*info) for info in zip(*args)]

    def displacements(self):
        return [abs(target - start)
                for target, start in zip(self.target_positions, self.start_positions)]

    def start(self):
        return self.group.start_move(self.target_positions)

    def update(self):
        self.status = self._get_status()
        return self.status

    def in_motion(self):
        return any(status.state.is_moving() for status in self.status)


class BackAndForth(BaseMotion):

    def __init__(self, obj, ranges, sync_stop=True,
                 on_start_stop=None, on_end_stop=None):
        super().__init__(obj, sync_stop, on_start_stop, on_end_stop)
        self.loop_nb = 0
        self.ranges = ranges
        self.initial_positions = self.group.get_pos()
        self._initial_motion = self._new_motion()
        self.base_positions = self._initial_motion.target_positions
        self.motion = None

    def _new_motion(self, factor=-1):
        target_positions = [
            int(initial + factor * rng / 2)
            for initial, rng in zip(self.initial_positions, self.ranges)
        ]
        return Motion(self.group, target_positions)

    @property
    def start_positions(self):
        motion = self._initial_motion if self.motion is None else self.motion
        return motion.start_positions

    @property
    def status(self):
        motion = self._initial_motion if self.motion is None else self.motion
        return motion.status

    @property
    def target_positions(self):
        motion = self._initial_motion if self.motion is None else self.motion
        return motion.target_positions

    def in_motion(self):
        return True

    def displacements(self):
        return self.ranges

    def start(self):
        factor = 1 if self.loop_nb % 2 else -1
        self.motion = self._new_motion(factor)
        self.loop_nb += 1
        return self.motion.start()

    def update(self):
        if self.motion is None:
            return self._initial_motion.update()
        status = self.motion.update()
        if not self.motion.in_motion():
            self.start()
        return status
