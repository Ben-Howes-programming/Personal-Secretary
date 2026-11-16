"""
theme.py
========
Purpose : The look of the app and the small building blocks every page shares
          (headers, figure strips, rows, badges, charts, the day ribbon).
Location: ui/theme.py
Used by : app.py and every file in views/
Design  : "Dusk". Twilight navy surfaces with a sodium-lamp amber accent, Bricolage
          Grotesque for headings and IBM Plex Sans for text. Chart colours are a
          colour-blind-checked set and always follow the same order.
"""

import html

import streamlit as st

# Colours ------------------------------------------------------------
BG, PANEL, RAISED, LINE = "#161d2b", "#1e2738", "#253048", "#2f3b55"
TEXT, MUTED, AMBER = "#e9edf5", "#9aa6bd", "#f0b45c"
GOOD, WARN, BAD, INFO = "#0ca30c", "#fab219", "#e66767", "#3987e5"
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"]
TONES = {"good": GOOD, "warn": WARN, "bad": BAD, "info": INFO, "neutral": MUTED, "accent": AMBER}

CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

html, body, .stApp, [data-testid="stSidebar"] {{ font-family: 'IBM Plex Sans', system-ui, sans-serif; }}
h1, h2, h3, h4, .ps-title {{ font-family: 'Bricolage Grotesque', 'IBM Plex Sans', system-ui, sans-serif !important; letter-spacing: -0.01em; }}
.block-container {{ padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1280px; }}
[data-testid="stSidebar"] {{ border-right: 1px solid {LINE}; }}
[data-testid="stSidebarNav"] a {{ border-radius: 6px; }}

/* Primary buttons: dark text on amber so they stay readable */
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"],
[data-testid="stBaseButton-primary"] {{ color: #1c1404 !important; font-weight: 600; border: 0; }}
.stButton button, .stFormSubmitButton button, .stDownloadButton button {{ border-radius: 6px; }}
:focus-visible {{ outline: 2px solid {AMBER}; outline-offset: 2px; }}

.ps-head {{ margin: 0 0 1.4rem 0; }}
.ps-title {{ font-size: 2.3rem; font-weight: 700; line-height: 1.1; color: {TEXT}; margin: 0; }}
.ps-sub {{ color: {MUTED}; font-size: 1rem; margin-top: .35rem; }}

/* Figure strip: one ruled band, not a row of boxes */
.ps-kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); border-top: 1px solid {LINE};
            border-bottom: 1px solid {LINE}; margin: 0 0 1.6rem 0; }}
.ps-kpi {{ padding: .9rem 1.1rem .95rem 0; margin-left: 1.1rem; border-left: 1px solid {LINE}; padding-left: 1.1rem; }}
.ps-kpi:first-child {{ margin-left: 0; border-left: 0; padding-left: 0; }}
.ps-kpi .v {{ font-family: 'Bricolage Grotesque', sans-serif; font-size: 1.75rem; font-weight: 700; color: {TEXT};
              font-variant-numeric: tabular-nums; line-height: 1.15; }}
.ps-kpi .l {{ color: {MUTED}; font-size: .86rem; }}
.ps-kpi .n {{ font-size: .82rem; margin-top: .15rem; font-variant-numeric: tabular-nums; }}

.ps-section {{ font-family: 'Bricolage Grotesque', sans-serif; font-size: 1.15rem; font-weight: 700; color: {TEXT};
               margin: 1.2rem 0 .5rem 0; }}
.ps-row {{ display: flex; gap: .8rem; align-items: baseline; padding: .55rem .2rem .55rem .8rem; border-bottom: 1px solid {LINE};
           border-left: 3px solid transparent; }}
.ps-row .t {{ color: {TEXT}; flex: 1; min-width: 0; }}
.ps-row .m {{ color: {MUTED}; font-size: .86rem; }}
.ps-row .r {{ color: {MUTED}; font-size: .86rem; white-space: nowrap; font-variant-numeric: tabular-nums; }}
.ps-badge {{ display: inline-block; font-size: .76rem; font-weight: 600; padding: .08rem .5rem; border-radius: 999px;
             border: 1px solid currentColor; margin-right: .3rem; white-space: nowrap; }}
.ps-note {{ border-left: 3px solid {MUTED}; background: {PANEL}; padding: .6rem .9rem; border-radius: 0 6px 6px 0;
            margin: .4rem 0; color: {TEXT}; }}
.ps-empty {{ color: {MUTED}; padding: 1rem 0; }}
.ps-empty b {{ color: {TEXT}; font-weight: 600; }}
.ps-muted {{ color: {MUTED}; font-size: .86rem; }}

/* Day ribbon */
.ps-ribbon {{ position: relative; height: 62px; background: {PANEL}; border-radius: 10px; margin: .2rem 0 1.9rem 0; }}
.ps-ribbon .ev {{ position: absolute; top: 9px; height: 30px; background: {INFO}; border-radius: 4px; color: #fff;
                  font-size: .74rem; padding: 0 .35rem; line-height: 30px; overflow: hidden; white-space: nowrap;
                  text-overflow: ellipsis; box-shadow: 0 0 0 2px {PANEL}; }}
.ps-ribbon .ev.plan {{ background: transparent; border: 1.5px dashed {AMBER}; color: {AMBER}; }}
.ps-ribbon .wind {{ position: absolute; top: 0; bottom: 0; background: repeating-linear-gradient(135deg, transparent 0 6px, rgba(240,180,92,.13) 6px 12px);
                    border-left: 1px solid {AMBER}; border-radius: 0 10px 10px 0; }}
.ps-ribbon .now {{ position: absolute; top: -5px; bottom: -5px; width: 2px; background: {AMBER}; }}
.ps-ribbon .now span {{ position: absolute; top: -17px; left: -18px; width: 38px; text-align: center; font-size: .72rem;
                        color: {AMBER}; font-weight: 600; }}
.ps-ribbon .tick {{ position: absolute; bottom: -19px; font-size: .72rem; color: {MUTED}; transform: translateX(-50%); }}
@media (max-width: 640px) {{ .ps-title {{ font-size: 1.7rem; }} .ps-kpi .v {{ font-size: 1.35rem; }} }}
"""


def esc(value):
    """Make any text safe to place inside HTML (email subjects are untrusted)."""
    return html.escape(str(value if value is not None else ""))


def inject():
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def _html(markup):
    st.markdown(markup, unsafe_allow_html=True)


# Text blocks ----------------------------------------------------------
def header(title, subtitle=""):
    sub = f'<div class="ps-sub">{esc(subtitle)}</div>' if subtitle else ""
    _html(f'<div class="ps-head"><h1 class="ps-title">{esc(title)}</h1>{sub}</div>')


def section(title):
    _html(f'<div class="ps-section">{esc(title)}</div>')


def kpis(items):
    """A strip of headline figures. Each item: (label, value) or (label, value, note, tone)."""
    cells = []
    for item in items:
        label, value = item[0], item[1]
        note = item[2] if len(item) > 2 else ""
        tone = TONES.get(item[3], MUTED) if len(item) > 3 else MUTED
        note_html = f'<div class="n" style="color:{tone}">{esc(note)}</div>' if note else ""
        cells.append(f'<div class="ps-kpi"><div class="v">{esc(value)}</div><div class="l">{esc(label)}</div>{note_html}</div>')
    _html(f'<div class="ps-kpis">{"".join(cells)}</div>')


def badge(text, tone="neutral"):
    return f'<span class="ps-badge" style="color:{TONES.get(tone, MUTED)}">{esc(text)}</span>'


def row(title, meta="", right="", tone=None, badges=""):
    """One line in a list: title, optional small text under it, optional right-hand value."""
    bar = f"border-left-color:{TONES[tone]};" if tone in TONES else ""
    meta_html = f'<div class="m">{esc(meta)}</div>' if meta else ""
    return (f'<div class="ps-row" style="{bar}"><div class="t">{badges}{esc(title)}{meta_html}</div>'
            f'<div class="r">{esc(right)}</div></div>')


def rows(markup_list):
    _html("".join(markup_list))


def note(tone, text):
    _html(f'<div class="ps-note" style="border-left-color:{TONES.get(tone, MUTED)}">{esc(text)}</div>')


def empty(text, hint=""):
    _html(f'<div class="ps-empty"><b>{esc(text)}</b> {esc(hint)}</div>')


def muted(text):
    _html(f'<div class="ps-muted">{esc(text)}</div>')


# Numbers --------------------------------------------------------------
def money(value, places=0):
    if value is None:
        return "not set"
    sign = "-" if value < 0 else ""
    return f"{sign}£{abs(value):,.{places}f}"


def pct(value, places=1):
    return "n/a" if value is None else f"{value:+.{places}f}%"


def tone_of(value):
    if value is None:
        return "neutral"
    return "good" if value > 0 else ("bad" if value < 0 else "neutral")


# Widgets that should fill their column -------------------------------
def _wide(function, *args, **kwargs):
    """Newer Streamlit uses width="stretch", older uses use_container_width=True."""
    try:
        return function(*args, width="stretch", **kwargs)
    except TypeError:
        return function(*args, use_container_width=True, **kwargs)


def button(label, **kwargs):
    return _wide(st.button, label, **kwargs)


def submit(label, **kwargs):
    return _wide(st.form_submit_button, label, **kwargs)


def table(data, **kwargs):
    return _wide(st.dataframe, data, hide_index=True, **kwargs)


# Charts ---------------------------------------------------------------
def _axis_style(alt):
    x_axis = alt.Axis(grid=False, labelColor=MUTED, tickColor=LINE, domainColor=LINE, title=None)
    y_axis = alt.Axis(gridColor=LINE, gridOpacity=0.6, labelColor=MUTED, titleColor=MUTED, domain=False, ticks=False, tickCount=5)
    return x_axis, y_axis


def _colour(alt, frame, order):
    """Fixed colour per series name, in a stable order, with a legend only when there are two or more."""
    if "series" not in frame.columns:
        return alt.value(SERIES[0])
    present = list(dict.fromkeys(frame["series"]))
    reference = list(order) if order else list(present)      # the full, fixed order
    reference += [name for name in present if name not in reference]
    shown = [name for name in reference if name in present]
    # A series keeps the colour of its place in the full order, even when others are hidden
    colours = [SERIES[reference.index(name) % len(SERIES)] for name in shown]
    legend = alt.Legend(orient="top", title=None, labelColor=TEXT, symbolStrokeWidth=3) if len(shown) > 1 else None
    return alt.Color("series:N", scale=alt.Scale(domain=shown, range=colours), legend=legend)


def line_chart(data, y_title="", order=None, height=280, number_format=",.2f"):
    """Line chart from rows of {date, value, series (optional)}. Hover a point for its value."""
    import altair as alt
    import pandas as pd
    frame = pd.DataFrame(data)
    if frame.empty:
        return empty("Nothing to plot yet.")
    x_axis, y_axis = _axis_style(alt)
    colour = _colour(alt, frame, order)
    tips = [alt.Tooltip("date:T", title="Date"), alt.Tooltip("value:Q", title=y_title or "Value", format=number_format)]
    if "series" in frame.columns:
        tips.insert(0, alt.Tooltip("series:N", title="Series"))
    base = alt.Chart(frame).encode(x=alt.X("date:T", axis=x_axis),
                                   y=alt.Y("value:Q", title=y_title or None, axis=y_axis, scale=alt.Scale(zero=False)))
    lines = base.mark_line(strokeWidth=2).encode(color=colour)
    targets = base.mark_circle(size=160, opacity=0).encode(color=colour, tooltip=tips)   # large invisible hover targets
    chart = (lines + targets).properties(height=height, background="transparent").configure_view(strokeOpacity=0)
    _wide(st.altair_chart, chart)


def bar_chart(data, y_title="", order=None, height=260, number_format=",.1f", stacked=True):
    """Bars from rows of {label, value, series (optional)}. Labels keep the order given."""
    import altair as alt
    import pandas as pd
    frame = pd.DataFrame(data)
    if frame.empty:
        return empty("Nothing to plot yet.")
    x_axis, y_axis = _axis_style(alt)
    x_axis = alt.Axis(grid=False, labelColor=MUTED, tickColor=LINE, domainColor=LINE, title=None, labelAngle=0)
    tips = [alt.Tooltip("label:N", title=""), alt.Tooltip("value:Q", title=y_title or "Value", format=number_format)]
    if "series" in frame.columns:
        tips.insert(1, alt.Tooltip("series:N", title="Series"))
    chart = alt.Chart(frame).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, stroke=BG, strokeWidth=2).encode(
        x=alt.X("label:N", sort=None, axis=x_axis, scale=alt.Scale(paddingInner=0.35)),
        y=alt.Y("value:Q", title=y_title or None, axis=y_axis, stack="zero" if stacked else None),
        color=_colour(alt, frame, order), tooltip=tips,
    ).properties(height=height, background="transparent").configure_view(strokeOpacity=0)
    _wide(st.altair_chart, chart)


# Day ribbon -----------------------------------------------------------
def day_ribbon(blocks, now, bedtime="23:30", start_hour=6):
    """Today from 06:00 to midnight as one bar.

    blocks : [{"start": datetime, "end": datetime, "label": str, "planned": bool}]
    Shows calendar events as solid blocks, suggested sessions as dashed blocks,
    the wind-down hour before bedtime as a hatched zone, and a marker for now.
    """
    span = (24 - start_hour) * 60

    def position(moment):
        minutes = moment.hour * 60 + moment.minute - start_hour * 60
        return max(0.0, min(100.0, minutes / span * 100))

    parts = []
    bed_hour, bed_minute = int(bedtime[:2]), int(bedtime[3:5])
    if bed_hour >= 12:
        wind = max(0.0, ((bed_hour * 60 + bed_minute - 60) - start_hour * 60) / span * 100)
        parts.append(f'<div class="wind" style="left:{wind:.2f}%;right:0" title="Wind down: bedtime target {esc(bedtime)}"></div>')
    for block in blocks:
        left, right = position(block["start"]), position(block["end"])
        if block["end"].date() > block["start"].date():
            right = 100.0
        if right - left < 0.6:
            continue
        css = "ev plan" if block.get("planned") else "ev"
        label = f'{block["start"].strftime("%H:%M")} {block["label"]}'
        parts.append(f'<div class="{css}" style="left:{left:.2f}%;width:{right - left:.2f}%" title="{esc(label)}">{esc(block["label"])}</div>')
    if now.hour >= start_hour:
        parts.append(f'<div class="now" style="left:{position(now):.2f}%"><span>{now.strftime("%H:%M")}</span></div>')
    for hour in range(start_hour, 25, 3):
        place = (hour - start_hour) * 60 / span * 100
        shift = "0" if hour == start_hour else ("-100%" if hour == 24 else "-50%")   # keep the end labels inside the bar
        parts.append(f'<div class="tick" style="left:{place:.2f}%;transform:translateX({shift})">{hour % 24:02d}:00</div>')
    _html(f'<div class="ps-ribbon" role="img" aria-label="Timeline of today">{"".join(parts)}</div>')


def days_until(iso_date, today):
    """'in 3 days', 'today', '2 days ago' for a YYYY-MM-DD string."""
    from datetime import date
    try:
        gap = (date.fromisoformat(iso_date) - today).days
    except (TypeError, ValueError):
        return ""
    if gap == 0:
        return "today"
    if gap == 1:
        return "tomorrow"
    if gap == -1:
        return "yesterday"
    return f"in {gap} days" if gap > 0 else f"{-gap} days ago"
