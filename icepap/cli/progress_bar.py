from prompt_toolkit.styles import Style
from prompt_toolkit.shortcuts import ProgressBar
from prompt_toolkit.layout.dimension import D
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.shortcuts.progress_bar.formatters import (
    Formatter,
    Label,
    Text,
    Percentage,
    Progress,
    Bar,
    TimeLeft
)


class Position(Formatter):

    moving = "<moving>{}</moving>"
    stopped = "<stopped>{}</stopped>"

    def format(self, progress_bar, progress, width):
        status = progress.motion_status
        template = self.moving if status.state.is_moving() else self.stopped
        pos = "{{:>{}}}".format(width).format(status.pos)
        return HTML(template).format(pos)

    def get_width(self, progress_bar):
        lengths = [len(str(c.motion_status.start)) for c in progress_bar.counters]
        lengths += [len(str(c.motion_status.target)) for c in progress_bar.counters]
        return D.exact(max(lengths))


class Start(Formatter):

    def format(self, progress_bar, progress, width):
        return "{{:>{}}}".format(width).format(progress.motion_status.start)

    def get_width(self, progress_bar):
        lengths = (len(str(c.motion_status.start)) for c in progress_bar.counters)
        return D.exact(max(lengths))


class Target(Formatter):

    def format(self, progress_bar, progress, width):
        return "{{:>{}}}".format(width).format(progress.motion_status.target)

    def get_width(self, progress_bar):
        lengths = (len(str(c.motion_status.target)) for c in progress_bar.counters)
        return D.exact(max(lengths))


class Range(Formatter):

    def __init__(self, template="{start} => {target}"):
        self.template = template

    def text(self, status):
        return self.template.format(start=status.start, target=status.target)

    def format(self, progress_bar, progress, width):
        return self.text(progress.motion_status)

    def get_width(self, progress_bar):
        lengths = (len(self.text(c.motion_status)) for c in progress_bar.counters)
        return D.exact(max(lengths))


def create_default_formatters():
    """
    Return the list of default formatters.
    """
    return [
        Label(),
        Text(" ["),
        Start(),
        Text(" => "),
        Target(),
        Text("] "),
        Position(),
        Text(" | "),
        Percentage(),
        Text(" "),
        Bar(sym_a="=", sym_b=">", sym_c=" "),
        Text(" "),
        Progress(),
        Text(" "),
        Text("eta [", style="class:time-left"),
        TimeLeft(),
        Text("]", style="class:time-left"),
        Text(" "),
    ]


FORMATTERS = create_default_formatters()
STYLE = Style.from_dict({
    "moving": "DeepSkyBlue bold",
    "stopped": "",
    "time-left": "DarkKhaki"
})

class Title:

    MOVING, STOPPING, STOPPED = range(3)

    def __init__(self, motion):
        self.motion = motion
        self.state = self.MOVING
        self.err = None

    def error_title(self):
        if type(self.err) is KeyboardInterrupt:
            title = 'Ctrl-C pressed'
        else:
            title = 'Motion error: {!r}'.format(self.err)
        return "<Orange>{}. Stopped all motors</Orange>. Waiting for motors to stop...".format(title)

    def __call__(self):
        if self.state == self.MOVING:
            if self.motion.in_motion():
                title = "<DeepSkyBlue>Moving...</DeepSkyBlue>"
            else:
                title = "<DarkKhaki>Preparing...</DarkKhaki>"
        elif self.state == self.STOPPING:
            title = self.error_title()
        elif self.state == self.STOPPED:
            title = self.error_title() + " [<Green>DONE</Green>]"
        return HTML(title)


def MotionBar(motion, *args, **kwargs):
    title = Title(motion)

    def update(status):
        for bar, status in zip(bars, status):
            bar.motion_status = status
            bar.items_completed = abs(status.pos - status.start)
        progbar.invalidate()

    def on_start_stop(exc_type, exc_value, tb):
        title.state = title.STOPPING
        title.err = exc_value

    def on_end_stop():
        title.state = title.STOPPED

    motion.on_start_stop = on_start_stop
    motion.on_end_stop = on_end_stop

    kwargs.setdefault("formatters", FORMATTERS)
    kwargs.setdefault("style", STYLE)
    kwargs.setdefault("title", title)
    progbar = ProgressBar(*args, **kwargs)
    progbar.update = update
    bars = []
    label_template = "{status.name}(#{status.motor.axis})"
    for status, total in zip(motion.status, motion.displacements()):
        label = label_template.format(status=status)
        bar = progbar(label=label, total=max(1, total))
        if total == 0:
            bar.items_completed = 1
            bar.done = True
        bar.motion_status = status
        bars.append(bar)
    return progbar
