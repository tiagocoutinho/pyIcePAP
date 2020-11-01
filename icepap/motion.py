from collections import namedtuple

from .group import group


MotorMotionState = namedtuple(
    "MotorMotionState", "motor name state pos start target"
)


class Motion:

    def __init__(self, obj, target_positions, sync_stop=True,
                 on_start_stop=None, on_end_stop=None):
        self.group = group(obj)
        self.target_positions = target_positions
        self.sync_stop = sync_stop
        self.on_start_stop = on_start_stop or (lambda *args: None)
        self.on_end_stop = on_end_stop or (lambda *args: None)
        self.start_positions = pos = self.group.get_pos()
        self.status = self._get_status(pos=pos, start=pos)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_value is not None:
            self._stop(exc_type, exc_value, traceback)

    def _stop(self, exc_type=None, exc_value=None, traceback=None):
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

    def stop(self):
        return self._stop()

    def update(self):
        self.status = self._get_status()
        return self.status

    def in_motion(self):
        return any(status.state.is_moving() for status in self.status)
