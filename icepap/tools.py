import contextlib

from .group import group


@contextlib.contextmanager
def ensure_power(obj, on=True):
    """
    Power context manager. Entering context ensures the motor(s) have power
    (or an exception is thrown). Leaving the context leaves motor(s) has we
    found them. The context manager object is an icepap.Group.

    :param obj: a Group, IcePAPAxis or a sequence of IcePAPAxis
    :param on: if True, ensures power on all motors and when leaving the
               context restores power off on the motors  that were powered
               of before. If False the reverse behavior is applied

    Example::

        from icepap import IcePAPController, ensure_power
        ipap = IcePAPController('ipap.acme.com')
        m1, m2 = ipap[1], ipap[2]
        m1.power = False
        m2.power = True
        assert (m1.power, m2.power) == (False, True)
        with ensure_power((m1, m2)) as group:
            assert (m1.power, m2.power) == (True, True)
            group.start_move((1000, 2000))
            group.wait_move()
        assert (m1.power, m2.power) == (False, True)
    """
    g = group(obj)
    to_power = [addr for addr, power in zip(g.axes, g.powers) if power != on]
    if to_power:
        g.controller.set_power(to_power, on)
    yield g
    if to_power:
        g.controller.set_power(to_power, not on)
