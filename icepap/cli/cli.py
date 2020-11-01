import time
import shutil
import itertools
import contextlib

import click
import beautifultable

from icepap.group import Group
from icepap.motion import Motion, BackAndForth
from icepap.controller import IcePAPController

from .tools import ensure_power
from .progress_bar import MotionBar, BackAndForthBar

CLEAR_LINE = '\x1b[2K'


def _start_stop(etype, evalue, tb):
    kb = etype is KeyboardInterrupt
    if evalue is not None:
        err = 'Ctrl-C pressed' if kb else 'Error: {!r}'.format(evalue)
        click.secho('\n{}. Stopping all motors'.format(err), fg="red")
    click.echo('Waiting for motors to stop... ', nl=False)


def _end_stop():
    click.echo('[DONE]')


def _motion_pos_human(motion):
    messages = []
    group = motion.group
    args = (group.motors, group.get_names(), group.get_states(),
            motion.start_positions, group.get_fpos(), motion.target_positions)
    for motor, name, state, start, pos, target in zip(*args):
        fg = "bright_blue" if state.is_moving() else None
        str_pos = click.style(str(pos), fg=fg)
        msg = '{}[{} => {}]: {}'.format(name, start, target, str_pos)
        messages.append(msg)
    return ' | '.join(messages)


def _umove(group, positions):
    with contextlib.ExitStack() as stack:
        power = ensure_power(group)
        motion = Motion(group, positions,
                        on_start_stop=_start_stop,
                        on_end_stop=_end_stop)
        stack.enter_context(power)
        stack.enter_context(motion)
        motion.start()
        last_update = 0
        try:
            while motion.in_motion():
                nap = 0.1 - (time.monotonic() - last_update)
                if nap > 0:
                    time.sleep(nap)
                click.echo('{}{}\r'.format(CLEAR_LINE, _motion_pos_human(
                    motion)), nl=False)
                last_update = time.monotonic()
        finally:
            click.echo('\r{}{}'.format(CLEAR_LINE, _motion_pos_human(motion)))


def umove(*pair_motor_pos):
    motors, positions = pair_motor_pos[::2], pair_motor_pos[1::2]
    _umove(Group(motors), positions)


def _pmove(group, positions, refresh_period=0.1):
    power = ensure_power(group)
    motion = Motion(group, positions)
    progbar = MotionBar(motion)
    with progbar:
        try:
            with power, motion:
                last_update, in_motion = 0, True
                while in_motion:
                    nap = refresh_period - (time.monotonic() - last_update)
                    if nap > 0:
                        time.sleep(nap)
                    progbar.update(motion.update())
                    in_motion = motion.in_motion()
                    last_update = time.monotonic()
        finally:
            progbar.update(motion.update())


def pmove(*pair_motor_pos):
    motors, positions = pair_motor_pos[::2], pair_motor_pos[1::2]
    _pmove(Group(motors), positions)


def _pshake(group, ranges, refresh_period=0.1):
    power = ensure_power(group)
    motion = BackAndForth(group, ranges)
    progbar = BackAndForthBar(motion)
    with progbar:
        try:
            with power, motion:
                last_update, in_motion = 0, True
                while in_motion:
                    nap = refresh_period - (time.monotonic() - last_update)
                    if nap > 0:
                        time.sleep(nap)
                    progbar.update(motion.update())
                    in_motion = motion.in_motion()
                    last_update = time.monotonic()
        finally:
            progbar.update(motion.update())


def pshake(*pair_motor_range):
    motors, ranges = pair_motor_range[::2], pair_motor_range[1::2]
    _pshake(Group(motors), ranges)

# ------

def Table(headers=(), **kwargs):
    style = kwargs.pop('style', beautifultable.STYLE_BOX_ROUNDED)
    if isinstance(style, str):
        style = beautifultable.Style['STYLE_{}'.format(style.upper())]
    table = beautifultable.BeautifulTable(
        max_width=shutil.get_terminal_size().columns - 1,
        default_alignment=beautifultable.ALIGN_RIGHT, default_padding=1)
    table.column_headers = headers
    table.column_alignments[headers[0]] = beautifultable.ALIGN_LEFT
    table.set_style(style)
    return table


def bool_text(data, false='NO', true='YES'):
    return true if data else false


def bool_text_color(data, text_false='NO', text_true='YES',
                    color_false="bright_red",
                    color_true="green"):
    color = color_true if data else color_false
    text = bool_text(data, text_false, text_true)
    text = click.style(text, fg=color)
    return text


def bool_text_color_inv(data, text_false='NO', text_true='YES'):
    return bool_text_color(data, text_false, text_true,
                           "green",
                           "bright_red")


def _stat_table(*motors, style='BOX_ROUNDED'):
    headers = ('Addr', 'Name', 'Pos.', 'Ready', 'Alive', 'Pres.', 'Enab.',
               'Power', '5V', 'Lim-', 'Lim+', 'Warn')
    group = Group(motors)
    table = Table(headers, style=style)
    args = (group.motors, group.get_names(), group.get_states(), group.get_fpos())
    for motor, name, state, pos in zip(*args):
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
    click.echo(_stat_table(*motors, style=style))


def _info_table(*motors, style='BOX_ROUNDED'):
    headers = ('Addr', 'Name', 'Pos.', 'Ready', 'Vel.', 'Acc. T.')
    data = []
    group = Group(motors)
    table = Table(headers, style=style)
    args = (group.motors, group.get_names(), group.get_states(), group.get_fpos(),
            group.get_acctime(), group.get_velocity())
    for motor, name, state, pos, acctime, velocity in zip(*args):
        row = (motor.axis, name, pos,
               bool_text_color(state.is_ready()), velocity, acctime)
        table.append_row(row)
    return table


def _info(*motors, style='BOX_ROUNDED'):
    click.echo(_info_table(*motors, style=style))


def _to_axes_arg(pap, axes):
    if axes == 'all':
        axes = pap.find_axes(only_alive=False)
    elif axes == 'alive':
        axes = pap.find_axes(only_alive=True)
    else:
        axes = (int(i) for i in axes.split(','))
    return axes


# -----


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
def move(ctx, pairs, bar):
    pap = ctx.obj['icepap']
    motors = [pap[int(address)] for address in pairs[::2]]
    positions = [int(position) for position in pairs[1::2]]
    func = _pmove if bar else _umove
    func(Group(motors), positions)


@cli.command()
@click.argument('pairs', nargs=-1, type=int)
@click.pass_context
def shake(ctx, pairs):
    pap = ctx.obj['icepap']
    motors = [pap[int(address)] for address in pairs[::2]]
    ranges = [int(rang) for rang in pairs[1::2]]
    _pshake(Group(motors), ranges)


@cli.command()
@click.argument('pairs', nargs=-1, type=int)
@click.option('--bar', is_flag=True)
@click.pass_context
def rmove(ctx, pairs, bar):
    raise NotImplementedError


@cli.command()
@click.argument('axes', nargs=-1, type=int)
@click.option('--async')
@click.pass_context
def jog(ctx, axes):
    raise NotImplementedError


@cli.command()
@click.argument('axes', nargs=-1, type=int)
@click.pass_context
def stop(ctx, axes):
    raise NotImplementedError


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
    motors = [pap[axis] for axis in axes]
    if compact or ascii:
        style = 'COMPACT'
    else:
        style = 'BOX_ROUNDED'
    _info(*motors, style=style)


if __name__ == '__main__':
    cli()
