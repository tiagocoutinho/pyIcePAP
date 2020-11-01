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


def MotionBar(motion, *args, **kwargs):
    def update(status):
        for bar, status in zip(bars, status):
            bar.motion_status = status
            bar.items_completed = abs(status.pos - status.start)
        progbar.invalidate()

    kwargs.setdefault("formatters", FORMATTERS)
    kwargs.setdefault("style", STYLE)
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
