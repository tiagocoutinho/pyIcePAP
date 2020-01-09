from .group import group


class Motion:

    def __init__(self, obj, target_positions, sync_stop=True,
                 on_start_stop=None, on_end_stop=None):
        self.group = group(obj)
        self.target_positions = target_positions
        self.sync_stop = sync_stop
        self.on_start_stop = on_start_stop or (lambda *args: None)
        self.on_end_stop = on_end_stop or (lambda *args: None)

    def __enter__(self):
        self.start_positions = self.group.fpositions
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

    @property
    def displacements(self):
        return [abs(target - start)
                for target, start in zip(self.target_positions, self.start_positions)]

    @property
    def in_motion(self):
        return self.group.is_moving

    def start(self):
        return self.group.start_move(self.target_positions)

    def stop(self):
        return self._stop()
