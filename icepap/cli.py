import time
import itertools
import contextlib

import tqdm
import blessings
import beautifultable

from .group import Group
from .tools import ensure_power
from .motion import Motion
from .controller import IcePAPController

CLEAR_LINE = '\x1b[2K'

terminal = blessings.Terminal()


class ProgressBar(tqdm.tqdm):

    monitor_interval = 0

    def close(self):
        super().close()
        for lock in self.get_lock().locks:
            try:
                lock.release()
            except:
                pass


def iter_move(group, positions, on_start_stop=None, on_end_stop=None):
    with contextlib.ExitStack() as stack:
        power = ensure_power(group)
        motion = Motion(group, positions,
                        on_start_stop=on_start_stop,
                        on_end_stop=on_end_stop)
        stack.enter_context(power)
        stack.enter_context(motion)
        yield motion
        motion.start()
        while motion.in_motion:
            yield motion


def _start_stop(etype, evalue, tb):
    kb = etype is KeyboardInterrupt
    if evalue is not None:
        err = 'Ctrl-C pressed' if kb else 'Error: {!r}'.format(evalue)
        print(terminal.red('\n{}. Stopping all motors'.format(err)))
    print('Waiting for motors to stop... ', end='', flush=True)


def _end_stop():
    print('[DONE]')


def _motion_pos_human(motion):
    messages = []
    group = motion.group
    for motor, name, state, start, pos, target in zip(group.motors, group.names,
                                                      group.states,
                                                      motion.start_positions,
                                                      group.fpositions,
                                                      motion.target_positions):
        color = terminal.bright_blue if state.is_moving() else lambda x: x
        msg ='{}[{} => {}]: {}'.format(name, start, target, color(str(pos)))
        messages.append(msg)
    return ' | '.join(messages)


def _umove(group, positions):
    try:
        with contextlib.ExitStack() as stack:
            power = ensure_power(group)
            motion = Motion(group, positions,
                            on_start_stop=_start_stop,
                            on_end_stop=_end_stop)
            stack.enter_context(power)
            stack.enter_context(motion)
            motion.start()
            while motion.in_motion:
                print('{}{}'.format(CLEAR_LINE, _motion_pos_human(motion)), end='\r', flush=True)
                time.sleep(0.1)
    finally:
        print('\r{}{}'.format(CLEAR_LINE, _motion_pos_human(motion)))


def _motion_progress_bars(group, motion, postfix):
    fmt = '{l_bar}{bar}| {elapsed}<{remaining}{postfix}'
    args = zip(group.motors, group.names, motion.start_positions,
               motion.target_positions)
    bars = []
    for i, (motor, name, start_pos, target_pos) in enumerate(args):
        desc = '{} ({:g} -> {:g})'.format(name, start_pos, target_pos)
        displ = abs(target_pos - start_pos)
        if displ == 0:
            bar = ProgressBar(range(1), position=i, bar_format=fmt,
                              postfix=postfix(start_pos), desc=desc)
            bar.update(1)
        else:
            bar = ProgressBar(total=displ, position=i, bar_format=fmt,
                              postfix=postfix(start_pos), desc=desc)
        bar.motor = motor
        bar.start_pos = start_pos
        bar.target_pos = target_pos
        bar.last_step = 0
        bars.append(bar)
    return bars


def _pmove(group, positions):
    def postfix(p):
        return dict(At='{:.3f}'.format(p))
    imove = iter_move(group, positions, _start_stop, _end_stop)
    motion = next(imove)
    with contextlib.ExitStack() as stack:
        bars = _motion_progress_bars(group, motion, postfix)
        for bar in bars:
            stack.enter_context(bar)
        for _ in imove:
            states, positions = group.states, group.fpositions
            args = zip(bars, states, positions)
            for bar, state, pos in args:
                bar.set_postfix(**postfix(pos))
                step = abs(pos - bar.start_pos)
                update = step - bar.last_step
                if update > 0:
                    bar.update(update)
                bar.last_step = step
            time.sleep(0.1)


def umove(*pair_motor_pos):
    motors, positions = pair_motor_pos[::2], pair_motor_pos[1::2]
    _umove(Group(motors), positions)


def pmove(*pair_motor_pos):
    motors, positions = pair_motor_pos[::2], pair_motor_pos[1::2]
    _pmove(Group(motors), positions)


#------

def Table(headers=(), **kwargs):
    style = kwargs.pop('style', beautifultable.STYLE_BOX_ROUNDED)
    if isinstance(style, str):
        style = beautifultable.Style['STYLE_{}'.format(style.upper())]
    table = beautifultable.BeautifulTable(
        max_width=terminal.width - 1,
        default_alignment=beautifultable.ALIGN_RIGHT, default_padding=1)
    table.column_headers = headers
    table.column_alignments[headers[0]] = beautifultable.ALIGN_LEFT
    table.set_style(style)
    return table


def bool_text(data, false='NO', true='YES'):
    return true if data else false


def bool_text_color(data, text_false='NO', text_true='YES',
                    color_false=terminal.bright_red,
                    color_true=terminal.green):
    color = color_true if data else color_false
    text = bool_text(data, text_false, text_true)
    text = color(text)
    # BeautifulTable does not understand "Set character set to US, ie \x1b(B
    text = text.replace('\x1b(B', '')
    return text


def bool_text_color_inv(data, text_false='NO', text_true='YES'):
    return bool_text_color(data, text_false, text_true,
                           terminal.green,
                           terminal.bright_red)


def _stat_table(*motors, style='BOX_ROUNDED'):
    headers = ('Addr', 'Name', 'Pos.', 'Ready', 'Alive', 'Pres.', 'Enab.',
               'Power', '5V', 'Lim-', 'Lim+', 'Warn')
    data = []
    group = Group(motors)
    table = Table(headers, style=style)
    for motor, name, state, pos in zip(group.motors, group.names,
                                       group.states, group.fpositions):
        row = (motor.axis, name, pos,
               bool_text_color(state.is_ready()),
               bool_text_color(state.is_alive()),
               bool_text_color(state.is_present()),
               bool_text_color(not state.is_disabled()),
               bool_text_color(state.is_poweron(), 'OFF', 'ON'),
               bool_text_color(state.is_5vpower()),
               bool_text_color_inv(state.is_limit_negative(), 'OFF', 'ON'),
               bool_text_color_inv(state.is_limit_positive(), 'OFF', 'ON'),
               bool_text_color_inv(state.is_warning()))
        table.append_row(row)
    return table


def stat(*motors, style='BOX_ROUNDED'):
    print(_stat_table(*motors, style=style))


def _info_table(*motors, style='BOX_ROUNDED'):
    headers = ('Addr', 'Name', 'Pos.', 'Ready', 'Vel.', 'Acc. T.')
    data = []
    group = Group(motors)
    table = Table(headers, style=style)
    data = zip(group.motors, group.names, group.states, group.fpositions,
               group.acctimes, group.velocities)
    for motor, name, state, pos, acctime, velocity in data:
        row = (motor.axis, name, pos,
               bool_text_color(state.is_ready()), velocity, acctime)
        table.append_row(row)
    return table


def _info(*motors, style='BOX_ROUNDED'):
    print(_info_table(*motors, style=style))


def _to_axes_arg(pap, axes):
    if axes == 'all':
        axes = pap.find_axes(only_alive=False)
    elif axes == 'alive':
        axes = pap.find_axes(only_alive=True)
    else:
        axes = (int(i) for i in axes.split(','))
    return axes

# -----
import click

@click.group()
@click.option('-h', '--host')
@click.option('-p', '--port', default=5000, type=click.IntRange(min=1, max=65535))
@click.pass_context
def cli(ctx, host, port):
    ctx.ensure_object(dict)
    ctx.obj['icepap'] = IcePAPController(host, port)


@cli.command()
@click.argument('pairs', nargs=-1, type=int)
@click.option('--bar', is_flag=True)
@click.pass_context
def umv(ctx, pairs, bar):
    pap = ctx.obj['icepap']
    motors = [pap[int(address)] for address in pairs[::2]]
    positions = [int(position) for position in pairs[1::2]]
    func = _pmove if bar else _umove
    func(Group(motors), positions)


@cli.command()
@click.option('--axes', type=str, default='all')
@click.option('--compact', type=str, default=False, is_flag=True)
@click.option('--ascii', type=str, default=False, is_flag=True)
@click.pass_context
def status(ctx, axes, compact, ascii):
    pap = ctx.obj['icepap']
    axes = _to_axes_arg(pap, axes)
    motors = (pap[axis] for axis in axes)
    if compact or ascii:
        style = 'COMPACT'
    else:
        style = 'BOX_ROUNDED'
    stat(*motors, style=style)


@cli.command()
@click.option('--axes', type=str, default='all')
@click.option('--compact', type=str, default=False, is_flag=True)
@click.option('--ascii', type=str, default=False, is_flag=True)
@click.pass_context
def info(ctx, axes, compact, ascii):
    pap = ctx.obj['icepap']
    axes = _to_axes_arg(pap, axes)
    motors = (pap[axis] for axis in axes)
    if compact or ascii:
        style = 'COMPACT'
    else:
        style = 'BOX_ROUNDED'
    _info(*motors, style=style)


if __name__ == '__main__':
    cli()
