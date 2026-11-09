"""
Generate the per-channel Phoebus pages opened from waveforms.bob (buttons in its right-hand column):

    dac_control.bob   per-DAC waveform length, mode, CW amplitude/phase and the common apply (per-DAC generator IOCs)
    rfdc_nco.bob      per-ADC and per-DAC NCO: RF frequency, phase, resulting NCO frequency and Nyquist zone
    llrf_loop.bob     amplitude and phase loop settings (rf_control registers) and measurements

    python3 epics/gen_screens.py                  # 8 ADCs / 8 DACs (ZCU208, LBL208)
    python3 epics/gen_screens.py --channels 16 --suffix _16   # e.g. ZCU216

The PV names are those of mimo_mts/ioc/base_ioc.py (doc/PVs.md); $(P) is the IOC prefix passed by the button.
"""

import argparse
from pathlib import Path
from xml.sax.saxutils import escape


class Screen:
    def __init__(self, name, width):
        self.name = name
        self.width = width
        self.widgets = []
        self.height = 0

    def _add(self, xml, y, h):
        self.widgets.append(xml)
        self.height = max(self.height, y + h)

    def title(self, text, y=0, h=40):
        self._add(
            f"""  <widget type="label" version="2.0.0">
    <name>Title</name>
    <class>TITLE</class>
    <text>{escape(text)}</text>
    <x use_class="true">0</x>
    <y use_class="true">{y}</y>
    <width>{self.width}</width>
    <height>{h}</height>
    <font use_class="true">
      <font name="Header 1" family="Liberation Sans" style="BOLD" size="22.0">
      </font>
    </font>
    <transparent use_class="true">true</transparent>
    <vertical_alignment>1</vertical_alignment>
  </widget>""",
            y,
            h,
        )

    def label(self, text, x, y, w, h=30, bold=False, center=False):
        font = (
            '\n    <font>\n      <font family="Liberation Sans" style="BOLD" size="14.0">\n      </font>\n    </font>'
            if bold
            else ""
        )
        self._add(
            f"""  <widget type="label" version="2.0.0">
    <name>Label</name>
    <text>{escape(text)}</text>
    <x>{x}</x>
    <y>{y}</y>
    <width>{w}</width>
    <height>{h}</height>{font}
    <horizontal_alignment>{1 if center else 0}</horizontal_alignment>
    <vertical_alignment>1</vertical_alignment>
  </widget>""",
            y,
            h,
        )

    def entry(self, pv, x, y, w=90, precision=0, tooltip="$(pv_name)"):
        self._add(
            f"""  <widget type="textentry" version="3.0.0">
    <name>Text Entry</name>
    <pv_name>{pv}</pv_name>
    <x>{x}</x>
    <y>{y}</y>
    <width>{w}</width>
    <height>30</height>
    <precision>{precision}</precision>
    <show_units>false</show_units>
    <horizontal_alignment>1</horizontal_alignment>
    <tooltip>{escape(tooltip)}</tooltip>
  </widget>""",
            y,
            30,
        )

    def update(self, pv, x, y, w=90, precision=0):
        self._add(
            f"""  <widget type="textupdate" version="2.0.0">
    <name>Text Update</name>
    <pv_name>{pv}</pv_name>
    <x>{x}</x>
    <y>{y}</y>
    <width>{w}</width>
    <height>30</height>
    <background_color>
      <color name="Write_Background" red="128" green="255" blue="255">
      </color>
    </background_color>
    <precision>{precision}</precision>
    <show_units>false</show_units>
    <horizontal_alignment>1</horizontal_alignment>
    <vertical_alignment>1</vertical_alignment>
    <wrap_words>false</wrap_words>
  </widget>""",
            y,
            30,
        )

    def choice(self, pv, x, y, w=200):
        self._add(
            f"""  <widget type="choice" version="2.0.0">
    <name>Choice Button</name>
    <pv_name>{pv}</pv_name>
    <x>{x}</x>
    <y>{y}</y>
    <width>{w}</width>
    <height>30</height>
    <items_from_pv>true</items_from_pv>
  </widget>""",
            y,
            30,
        )

    def bool_button(self, pv, x, y, bit=0, w=100, labels_from_pv=False):
        self._add(
            f"""  <widget type="bool_button" version="2.0.0">
    <name>Boolean Button</name>
    <pv_name>{pv}</pv_name>
    <bit>{bit}</bit>
    <labels_from_pv>{str(labels_from_pv).lower()}</labels_from_pv>
    <x>{x}</x>
    <y>{y}</y>
    <width>{w}</width>
    <height>30</height>
  </widget>""",
            y,
            30,
        )

    def led(self, pv, x, y, bit=0):
        self._add(
            f"""  <widget type="led" version="2.0.0">
    <name>LED</name>
    <pv_name>{pv}</pv_name>
    <bit>{bit}</bit>
    <x>{x}</x>
    <y>{y}</y>
    <width>30</width>
    <height>30</height>
  </widget>""",
            y,
            30,
        )

    def slider(self, pv, x, y, w, minimum, maximum):
        self._add(
            f"""  <widget type="scaledslider" version="2.0.0">
    <name>Scaled Slider</name>
    <pv_name>{pv}</pv_name>
    <x>{x}</x>
    <y>{y}</y>
    <width>{w}</width>
    <height>30</height>
    <show_minor_ticks>false</show_minor_ticks>
    <show_hihi>false</show_hihi>
    <show_high>false</show_high>
    <show_low>false</show_low>
    <show_lolo>false</show_lolo>
    <minimum>{minimum}</minimum>
    <maximum>{maximum}</maximum>
    <limits_from_pv>false</limits_from_pv>
  </widget>""",
            y,
            30,
        )

    def write_button(self, text, pv, value, x, y, w=160, tooltip=""):
        self._add(
            f"""  <widget type="action_button" version="3.0.0">
    <name>{escape(text)}</name>
    <actions>
      <action type="write_pv">
        <pv_name>{pv}</pv_name>
        <value>{value}</value>
        <description>{escape(text)}</description>
      </action>
    </actions>
    <text>{escape(text)}</text>
    <x>{x}</x>
    <y>{y}</y>
    <width>{w}</width>
    <height>30</height>
    <tooltip>{escape(tooltip)}</tooltip>
  </widget>""",
            y,
            30,
        )

    def xml(self):
        body = "\n".join(self.widgets)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<display version="2.0.0">
  <name>{escape(self.name)}</name>
  <width>{self.width}</width>
  <height>{self.height + 20}</height>
{body}
</display>
"""


def table(scr, y, columns):
    """Header row of (text, x, w); returns the y of the first data row."""
    for text, x, w in columns:
        scr.label(text, x, y, w, bold=True, center=text != columns[0][0])
    return y + 35


def dac_control(n):
    scr = Screen("DAC control", 1100)
    scr.title("$(P) DACs: waveform length, mode and CW")
    y = 55
    scr.label("All DACs length [ns]", 10, y, 150)
    scr.entry("$(P):DAC:wave_length", 160, y, 90, 0, "$(pv_name): pulse (single) or period (loop), 4 ns steps, 0 = all")
    scr.label("pulse_length [4 ns cycles]", 280, y, 180)
    scr.entry("$(P):rf_control:pulse_length", 460, y, 80)
    scr.update("$(P):rf_control:pulse_length:RBV", 545, y, 80)
    scr.write_button(
        "Apply modes / CW", "$(P):DAC:apply", 1, 660, y, 160,
        "Make the staged DAC modes and CW values active on all DACs at once ($(P):DAC:apply)",
    )  # fmt: skip
    scr.label("Fill all DACs", 10, 95, 110)
    scr.bool_button("$(P):DAC:fill_ones", 120, 95, w=120, labels_from_pv=True)
    scr.label(
        "Loads every DAC waveform at once: 'ones' = constant full-scale I (a CW at the DAC RF frequency once the DACs "
        "are enabled), 'zeros' = silent. Overwrites the per-DAC waveforms.",
        250, 95, 840, 40,
    )  # fmt: skip
    scr.label(
        "Modes and CW values are staged: set them for any DACs, then Apply (all DACs change on the same clock). "
        "CW frequency = DAC NCO RF frequency. Only on IOCs with one waveform generator per DAC.",
        10, 140, 1080, 25,
    )  # fmt: skip
    cols = [
        ("DAC", 10, 60),
        ("mode (staged)", 80, 200),
        ("active", 290, 90),
        ("CW amp (0-1)", 390, 110),
        ("CW phase [deg]", 510, 110),
        ("length [ns]", 630, 110),
        ("applied [ns]", 750, 110),
    ]
    y = table(scr, 170, cols)
    for ch in range(n):
        yy = y + 38 * ch
        scr.label(f"DAC{ch}", 10, yy, 60, bold=True)
        scr.choice(f"$(P):DAC{ch}:mode", 80, yy, 200)
        scr.update(f"$(P):DAC{ch}:mode:RBV", 290, yy, 90)
        scr.entry(f"$(P):DAC{ch}:cw:amp", 390, yy, 110, 3)
        scr.entry(f"$(P):DAC{ch}:cw:phase", 510, yy, 110, 1)
        scr.entry(f"$(P):DAC{ch}:wave_length", 630, yy, 110, 0, "$(pv_name): 4 ns steps, 0 = whole memory")
        scr.update(f"$(P):DAC{ch}:wave_length:RBV", 750, yy, 110, 0)
    return scr


def rfdc_nco(n):
    scr = Screen("RFDC NCO", 900)
    scr.title("$(P) per-channel NCO")
    scr.label(
        "Set the RF frequency (0 to the sampling rate, e.g. 3000 MHz); the IOC picks the NCO frequency and Nyquist "
        "zone. The all-channel setting overwrites the per-channel ones.",
        10, 45, 880, 40,
    )  # fmt: skip
    y = 95
    for conv in ("adc", "dac"):
        up = conv.upper()
        scr.label(f"All {up}s RF [MHz]", 10, y, 140, bold=True)
        scr.entry(f"$(P):rfdc_mixer:{conv}_rf_freq_mhz", 150, y, 100, 3)
        scr.update(f"$(P):rfdc_mixer:{conv}_rf_freq_mhz:RBV", 255, y, 100, 3)
        scr.label("phase [deg]", 380, y, 90)
        scr.entry(f"$(P):rfdc_mixer:{conv}_mixer_nco_phase", 470, y, 90, 1)
        scr.update(f"$(P):rfdc_mixer:{conv}_mixer_nco_phase:RBV", 565, y, 90, 1)
        cols = [
            (up, 10, 60),
            ("RF [MHz]", 80, 110),
            ("applied", 195, 100),
            ("phase [deg]", 310, 90),
            ("applied", 405, 90),
            ("NCO [MHz]", 510, 110),
            ("zone", 625, 60),
        ]
        yy = table(scr, y + 40, cols)
        for ch in range(n):
            row = yy + 38 * ch
            base = f"$(P):rfdc_mixer:{up}{ch}"
            scr.label(f"{up}{ch}", 10, row, 60, bold=True)
            scr.entry(f"{base}:rf_freq_mhz", 80, row, 110, 3)
            scr.update(f"{base}:rf_freq_mhz:RBV", 195, row, 100, 3)
            scr.entry(f"{base}:nco_phase", 310, row, 90, 1)
            scr.update(f"{base}:nco_phase:RBV", 405, row, 90, 1)
            scr.update(f"{base}:nco_freq_mhz:RBV", 510, row, 110, 3)
            scr.update(f"{base}:nco_nyquist:RBV", 625, row, 60, 0)
        y = yy + 38 * n + 25
    return scr


def llrf_loop():
    scr = Screen("LLRF loop", 900)
    scr.title("$(P) LLRF amplitude and phase loops")
    scr.label(
        "rf_control registers (raw values: setpoints, gains and errors in DSP units); blue fields are read back.",
        10, 45, 880, 25,
    )  # fmt: skip
    y = 80
    # setpoint slider ranges as on the earlier waveforms.bob
    loops = (("amp", "Amplitude loop", 0.0, 78000.0), ("phs", "Phase loop", -131072.0, 131071.0))
    for loop, title, smin, smax in loops:
        reg = f"$(P):rf_control:{loop}_loop"
        scr.label(title, 10, y, 300, bold=True)
        y += 35
        scr.label("enable", 10, y, 90)
        scr.bool_button(f"{reg}_enable", 100, y)
        scr.led(f"{reg}_enable:RBV", 210, y)
        scr.label("reset", 300, y, 60)
        scr.bool_button(f"{reg}_reset", 360, y)
        scr.led(f"{reg}_reset:RBV", 470, y)
        y += 38
        scr.label("setpoint", 10, y, 90)
        scr.entry(f"{reg}_setpoint", 100, y, 110)
        scr.update(f"{reg}_setpoint:RBV", 215, y, 110)
        scr.slider(f"{reg}_setpoint", 340, y, 300, smin, smax)
        y += 38
        scr.label("kp", 10, y, 90)
        scr.entry(f"{reg}_kp", 100, y, 110)
        scr.update(f"{reg}_kp:RBV", 215, y, 110)
        scr.label("ki", 340, y, 40)
        scr.entry(f"{reg}_ki", 380, y, 110)
        scr.update(f"{reg}_ki:RBV", 495, y, 110)
        y += 38
        scr.label("error", 10, y, 90)
        scr.update(f"{reg}_err:RBV", 100, y, 110)
        scr.label("measured", 340, y, 80)
        scr.update(f"$(P):rf_control:{loop}_measured:RBV", 420, y, 110)
        y += 55
    scr.label("RF status", 10, y, 90)
    scr.update("$(P):rf_control:rf_status:RBV", 100, y, 110)
    return scr


def main():
    parser = argparse.ArgumentParser(description="Generate the per-channel Phoebus pages.")
    parser.add_argument("--channels", type=int, default=8, help="ADCs and DACs per board")
    parser.add_argument("--suffix", default="", help="file name suffix, e.g. _16")
    args = parser.parse_args()
    out = Path(__file__).parent
    screens = (
        ("dac_control", dac_control(args.channels)),
        ("rfdc_nco", rfdc_nco(args.channels)),
        ("llrf_loop", llrf_loop()),
    )
    for name, scr in screens:
        path = out / f"{name}{args.suffix}.bob"
        path.write_text(scr.xml())
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
