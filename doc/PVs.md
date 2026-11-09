# EPICS Process Variables

The IOCs (`sudo -E {mimo,llrf}-{zcu208,lbl208,zcu216}-ioc`, `mimo-5g-zcu208-ioc`) publish the PVs below, all under
the IOC prefix `$P` (the overlay name, e.g. `ALS_LLRF_LBL208`). The tables at the end are generated from the IOC code
(`python -m mimo_mts.ioc.gen_pv_docs`, checked in CI); the notes here explain how to use each group.
Setpoints have a matching `:RBV` readback where the hardware can be read back.

## Waveforms

`ADC{n}:IWF` / `ADC{n}:QWF` are the raw captures of each ADC (int16 counts, time axis `ADC:TWF` in ns). `DSP:ADC{n}:AWF`
and `DSP:ADC{n}:PWF` are amplitude and phase after averaging by the IOC decimation (time axis `DSP:TWF`). They update
on every capture-done interrupt where the overlay has one, otherwise periodically.

## Pulse statistics

Set the window with `DSP:ADC{n}:pulse_stat:start_ns` and `end_ns` (on the `DSP:TWF` axis); the IOC publishes the mean
and standard deviation of amplitude and phase inside it for every capture.

## RF control

One PV per register of `axil_rf_control` / `axil_llrf` (`designs/ip/rtl/axil_rf_control.json`): trigger source,
period, delay and divider, pulse length, DAC/pulse enable, and the amplitude and phase loop settings. Values are the raw
register values (clock cycles of the DSP clock, loop gains and setpoints in DSP units). Read-only registers (status and
loop monitors) have only the `:RBV` PV.

## RFDC mixers

Operators set the RF frequency: `rfdc_mixer:adc_rf_freq_mhz` / `dac_rf_freq_mhz` for all ADCs or DACs,
`rfdc_mixer:{ADC,DAC}{n}:rf_freq_mhz` for one channel, in MHz between 0 and the sampling rate (e.g. 3000 for the ALS
carrier). The IOC derives the fine-mixer NCO frequency and the Nyquist zone from it (`mimo_mts/utils/rfdc_freq.py`):
zone 2 above Fs/2, where the spectrum is inverted, so 3 GHz at 4 GSPS becomes DAC NCO −3000 MHz, ADC NCO +3000 MHz,
zone 2. The `:RBV` is computed back from the NCO settings. The NCO PVs themselves (`rfdc_mixer:{adc,dac}_mixer_nco_*`,
`rfdc_mixer:{ADC,DAC}{n}:nco_*`: signed frequency in MHz, Nyquist zone 1 or 2, phase in degrees) remain for experts.

## DAC waveform, modes and CW

`DAC:IWF` and `DAC:QWF` are the I/Q baseband waveform (int16) for all DACs; writing either writes both (a shorter
array is padded with zeros). `DAC:TWF` is the time axis in ns at the complex input rate (DAC rate / interpolation).

On overlays with one waveform generator per DAC (`mimo_mts_5g`), each DAC also has:

- `DAC{n}:IWF` / `DAC{n}:QWF`: its own waveform (the shared `DAC:IWF` / `QWF` still write the same one to all DACs).
- `DAC{n}:mode`: `single` (play the waveform once per trigger), `loop` (a trigger starts playback that repeats until
  the mode changes) or `CW` (constant output); `DAC{n}:mode:RBV` is the mode in effect.
- `DAC{n}:cw:amp` (0–1, fraction of full scale) and `DAC{n}:cw:phase` (degrees): the CW amplitude and phase. The CW
  frequency is the DAC mixer frequency (`rfdc_mixer:DAC{n}:rf_freq_mhz` or `dac_rf_freq_mhz`).
- Mode and CW settings are staged: write them for any number of DACs, then `DAC:apply` = 1 makes all of them active
  on the same clock (phase-coherent changes across channels).

## RF-ADC calibration

On every IOC whose overlay has the RF Data Converter; background in `mimo_mts/drivers/adc_calibration.py` and
`doc/adc_calibration_findings.md`.

- `adc_cal:freeze` (all ADCs) or `adc_cal:ADC{n}:freeze` (one ADC): 1 freezes, 0 resumes GCB/TSCB background
  calibration; `adc_cal:ADC{n}:frozen:RBV` is the status reported by the RFDC.
- `adc_cal:save` / `adc_cal:restore`: write 1 to save all coefficients to `adc_cal:file`, or to restore GCB/TSCB from
  it and freeze. One file per board (default `/etc/mimo_mts/adc_cal.json`, set `MIMO_MTS_ADC_CAL_FILE` to change).
- `adc_cal:release_override`: write 1 to hand all calibration blocks back to the calibration engine.
- `adc_cal:status`: result of the last action.

At start, `AlsLlrfLBL208` freezes the calibration, re-runs the foreground calibration with the DAC drive off and
restores the saved coefficients if the file exists; the other IOCs leave background calibration tracking. To train:
apply a CW signal off the ALS carrier (above -40 dBFS, ideally near -10 dBFS), unfreeze, wait about 60 s, freeze and
save.

## Telemetry (LBL208)

Only `AlsLlrfLBL208`, under `$P:pmbus` with `$P` = `ALS_LLRF_LBL208`. Power-supply readings (read-only) with typical
values: `psu_vout` 12.1 V, `psu_vin` 122 V, `psu_iout` 2.3 A, `psu_iin` 0.3 A, `psu_pout` 28.6 W, `psu_pin` 35.5 W,
`psu_temperature_{1,2}` 24 °C, `psu_fan_speed_1` 4480 rpm. Which `psu_*` PVs exist depends on the sensors the power
supply reports; the table lists all the driver supports. `psu_status` is the 16-bit status word ([bit
definitions](../mimo_mts/drivers/telemetry/pmbus.py#L141)). The two chassis fans: `chassis_fan_speed_{1,2}` sets the
speed, `chassis_fan_speed_{1,2}:RBV` reads it, in rpm.

## PV reference (generated)

<!-- BEGIN GENERATED PV TABLES: python -m mimo_mts.ioc.gen_pv_docs -->

### IOCs

| IOC class | Entry point | Overlay | Prefix `$P` | ADCs / DACs | Records |
|---|---|---|---|---|---|
| `AlsLlrfZCU208` | `llrf-zcu208-ioc` | `ALS_LLRF_ZCU208` | `ALS_LLRF_ZCU208` | 8 / 8 | 288 |
| `AlsLlrfLBL208` | `llrf-lbl208-ioc` | `ALS_LLRF_LBL208` | `ALS_LLRF_LBL208` | 8 / 8 | 309 |
| `MimoZCU208` | `mimo-zcu208-ioc` | `MIMO_ZCU208` | `MIMO_ZCU208` | 8 / 8 | 288 |
| `Mimo5GZCU208` | `mimo-5g-zcu208-ioc` | `MIMO_5G_ZCU208` | `MIMO_5G_ZCU208` | 8 / 8 | 337 |
| `MimoLBL208` | `mimo-lbl208-ioc` | `MIMO_LBL208` | `MIMO_LBL208` | 8 / 8 | 288 |
| `MimoZCU216` | `mimo-zcu216-ioc` | `MIMO_ZCU216` | `MIMO_ZCU216` | 16 / 16 | 512 |

`{n}` is the ADC or DAC channel (0 to ADCs − 1 or DACs − 1 of the IOC), `{i}` the chassis fan (1, 2). All names start with `$P:`. Every IOC also has the standard `devIocStats` records under `$P:ioc`.

### DAC waveforms, modes and CW

| PV | Type | Description | Units | IOCs |
|---|---|---|---|---|
| `DAC:IWF` | waveform | DAC waveform I, all DACs | cnt | all |
| `DAC:QWF` | waveform | DAC waveform Q, all DACs | cnt | all |
| `DAC:TWF` | waveform | Time axis of the DAC waveform | ns | all |
| `DAC:apply` | bo | Apply staged DAC modes / CW, all DACs |  | `Mimo5GZCU208` |
| `DAC{n}:IWF` | waveform | DAC{n} waveform I | cnt | `Mimo5GZCU208` |
| `DAC{n}:QWF` | waveform | DAC{n} waveform Q | cnt | `Mimo5GZCU208` |
| `DAC{n}:cw:amp` | ao | DAC{n} CW amplitude (fraction of FS) |  | `Mimo5GZCU208` |
| `DAC{n}:cw:phase` | ao | DAC{n} CW phase | deg | `Mimo5GZCU208` |
| `DAC{n}:mode` | mbbo | DAC{n} mode (active on DAC:apply) |  | `Mimo5GZCU208` |
| `DAC{n}:mode:RBV` | mbbi | DAC{n} active mode |  | `Mimo5GZCU208` |

### ADC waveforms and time axes

| PV | Type | Description | Units | IOCs |
|---|---|---|---|---|
| `ADC:TWF` | waveform | Time axis of the ADC waveforms | ns | all |
| `ADC{n}:IWF` | waveform | ADC{n} captured I samples | cnt | all |
| `ADC{n}:QWF` | waveform | ADC{n} captured Q samples | cnt | all |
| `DSP:ADC{n}:AWF` | waveform | ADC{n} amplitude, decimated | cnt | all |
| `DSP:ADC{n}:PWF` | waveform | ADC{n} phase, decimated | deg | all |
| `DSP:TWF` | waveform | Time axis of the DSP waveforms | ns | all |

### Pulse statistics

| PV | Type | Description | Units | IOCs |
|---|---|---|---|---|
| `DSP:ADC{n}:pulse_stat:amp:mean` | ai | ADC{n} pulse amplitude mean | cnt | all |
| `DSP:ADC{n}:pulse_stat:amp:std` | ai | ADC{n} pulse amplitude std | cnt | all |
| `DSP:ADC{n}:pulse_stat:end_ns` | longout | ADC{n} pulse window end | ns | all |
| `DSP:ADC{n}:pulse_stat:phs:mean` | ai | ADC{n} pulse phase mean | deg | all |
| `DSP:ADC{n}:pulse_stat:phs:std` | ai | ADC{n} pulse phase std | deg | all |
| `DSP:ADC{n}:pulse_stat:start_ns` | longout | ADC{n} pulse window start | ns | all |

### RF control (`axil_rf_control` registers)

| PV | Type | Description | Units | IOCs |
|---|---|---|---|---|
| `rf_control:amp_loop_enable` | longout | Amplitude loop enable |  | all |
| `rf_control:amp_loop_enable:RBV` | longin | Amplitude loop enable |  | all |
| `rf_control:amp_loop_err:RBV` | longin | Amplitude loop error |  | all |
| `rf_control:amp_loop_ki` | longout | Amplitude loop integral gain |  | all |
| `rf_control:amp_loop_ki:RBV` | longin | Amplitude loop integral gain |  | all |
| `rf_control:amp_loop_kp` | longout | Amplitude loop proportional gain |  | all |
| `rf_control:amp_loop_kp:RBV` | longin | Amplitude loop proportional gain |  | all |
| `rf_control:amp_loop_reset` | longout | Amplitude loop reset |  | all |
| `rf_control:amp_loop_reset:RBV` | longin | Amplitude loop reset |  | all |
| `rf_control:amp_loop_setpoint` | longout | Amplitude loop setpoint |  | all |
| `rf_control:amp_loop_setpoint:RBV` | longin | Amplitude loop setpoint |  | all |
| `rf_control:amp_measured:RBV` | longin | Amplitude monitor |  | all |
| `rf_control:dac_enable` | longout | Bit0 DAC, bit1 pulse enable, bit2 apply |  | all |
| `rf_control:dac_enable:RBV` | longin | Bit0 DAC, bit1 pulse enable, bit2 apply |  | all |
| `rf_control:phs_loop_enable` | longout | Phase loop enable |  | all |
| `rf_control:phs_loop_enable:RBV` | longin | Phase loop enable |  | all |
| `rf_control:phs_loop_err:RBV` | longin | Phase loop error |  | all |
| `rf_control:phs_loop_ki` | longout | Phase loop integral gain |  | all |
| `rf_control:phs_loop_ki:RBV` | longin | Phase loop integral gain |  | all |
| `rf_control:phs_loop_kp` | longout | Phase loop proportional gain |  | all |
| `rf_control:phs_loop_kp:RBV` | longin | Phase loop proportional gain |  | all |
| `rf_control:phs_loop_reset` | longout | Phase loop reset |  | all |
| `rf_control:phs_loop_reset:RBV` | longin | Phase loop reset |  | all |
| `rf_control:phs_loop_setpoint` | longout | Phase loop setpoint |  | all |
| `rf_control:phs_loop_setpoint:RBV` | longin | Phase loop setpoint |  | all |
| `rf_control:phs_measured:RBV` | longin | Phase monitor |  | all |
| `rf_control:pulse_length` | longout | Pulse length in clock cycles |  | all |
| `rf_control:pulse_length:RBV` | longin | Pulse length in clock cycles |  | all |
| `rf_control:rf_status:RBV` | longin | Status register (bit 0 RF permit) |  | all |
| `rf_control:trig_delay` | longout | Trigger delay in clock cycles |  | all |
| `rf_control:trig_delay:RBV` | longin | Trigger delay in clock cycles |  | all |
| `rf_control:trig_divide` | longout | Trigger divider: use every n-th trigger |  | all |
| `rf_control:trig_divide:RBV` | longin | Trigger divider: use every n-th trigger |  | all |
| `rf_control:trig_period` | longout | Internal trigger period, cycles; 0 = off |  | all |
| `rf_control:trig_period:RBV` | longin | Internal trigger period, cycles; 0 = off |  | all |
| `rf_control:trig_sel` | longout | Trigger: 0 internal, 1 EVR, 2 external |  | all |
| `rf_control:trig_sel:RBV` | longin | Trigger: 0 internal, 1 EVR, 2 external |  | all |

### RFDC mixers

| PV | Type | Description | Units | IOCs |
|---|---|---|---|---|
| `rfdc_mixer:ADC{n}:nco_freq_mhz` | ao | ADC{n} NCO frequency | MHz | all |
| `rfdc_mixer:ADC{n}:nco_freq_mhz:RBV` | ai | ADC{n} NCO frequency | MHz | all |
| `rfdc_mixer:ADC{n}:nco_nyquist` | ao | ADC{n} Nyquist zone |  | all |
| `rfdc_mixer:ADC{n}:nco_nyquist:RBV` | ai | ADC{n} Nyquist zone |  | all |
| `rfdc_mixer:ADC{n}:nco_phase` | ao | ADC{n} NCO phase | deg | all |
| `rfdc_mixer:ADC{n}:nco_phase:RBV` | ai | ADC{n} NCO phase | deg | all |
| `rfdc_mixer:ADC{n}:rf_freq_mhz` | ao | ADC{n} RF frequency (sets NCO, zone) | MHz | all |
| `rfdc_mixer:ADC{n}:rf_freq_mhz:RBV` | ai | ADC{n} RF frequency | MHz | all |
| `rfdc_mixer:DAC{n}:nco_freq_mhz` | ao | DAC{n} NCO frequency | MHz | all |
| `rfdc_mixer:DAC{n}:nco_freq_mhz:RBV` | ai | DAC{n} NCO frequency | MHz | all |
| `rfdc_mixer:DAC{n}:nco_nyquist` | ao | DAC{n} Nyquist zone |  | all |
| `rfdc_mixer:DAC{n}:nco_nyquist:RBV` | ai | DAC{n} Nyquist zone |  | all |
| `rfdc_mixer:DAC{n}:nco_phase` | ao | DAC{n} NCO phase | deg | all |
| `rfdc_mixer:DAC{n}:nco_phase:RBV` | ai | DAC{n} NCO phase | deg | all |
| `rfdc_mixer:DAC{n}:rf_freq_mhz` | ao | DAC{n} RF frequency (sets NCO, zone) | MHz | all |
| `rfdc_mixer:DAC{n}:rf_freq_mhz:RBV` | ai | DAC{n} RF frequency | MHz | all |
| `rfdc_mixer:adc_mixer_nco_freq_mhz` | ao | All ADCs NCO frequency | MHz | all |
| `rfdc_mixer:adc_mixer_nco_freq_mhz:RBV` | ai | All ADCs NCO frequency | MHz | all |
| `rfdc_mixer:adc_mixer_nco_nyquist` | ao | All ADCs Nyquist zone |  | all |
| `rfdc_mixer:adc_mixer_nco_nyquist:RBV` | ai | All ADCs Nyquist zone |  | all |
| `rfdc_mixer:adc_mixer_nco_phase` | ao | All ADCs NCO phase | deg | all |
| `rfdc_mixer:adc_mixer_nco_phase:RBV` | ai | All ADCs NCO phase | deg | all |
| `rfdc_mixer:adc_rf_freq_mhz` | ao | All ADCs RF frequency (sets NCO, zone) | MHz | all |
| `rfdc_mixer:adc_rf_freq_mhz:RBV` | ai | All ADCs RF frequency | MHz | all |
| `rfdc_mixer:dac_mixer_nco_freq_mhz` | ao | All DACs NCO frequency | MHz | all |
| `rfdc_mixer:dac_mixer_nco_freq_mhz:RBV` | ai | All DACs NCO frequency | MHz | all |
| `rfdc_mixer:dac_mixer_nco_nyquist` | ao | All DACs Nyquist zone |  | all |
| `rfdc_mixer:dac_mixer_nco_nyquist:RBV` | ai | All DACs Nyquist zone |  | all |
| `rfdc_mixer:dac_mixer_nco_phase` | ao | All DACs NCO phase | deg | all |
| `rfdc_mixer:dac_mixer_nco_phase:RBV` | ai | All DACs NCO phase | deg | all |
| `rfdc_mixer:dac_rf_freq_mhz` | ao | All DACs RF frequency (sets NCO, zone) | MHz | all |
| `rfdc_mixer:dac_rf_freq_mhz:RBV` | ai | All DACs RF frequency | MHz | all |

### RF-ADC calibration

| PV | Type | Description | Units | IOCs |
|---|---|---|---|---|
| `adc_cal:ADC{n}:freeze` | bo | Freeze GCB/TSCB calibration, ADC{n} |  | all |
| `adc_cal:ADC{n}:frozen:RBV` | bi | ADC{n} calibration freeze status |  | all |
| `adc_cal:file` | waveform | Calibration file on the board |  | all |
| `adc_cal:freeze` | bo | Freeze GCB/TSCB calibration, all ADCs |  | all |
| `adc_cal:release_override` | bo | Return calibration to the engine |  | all |
| `adc_cal:restore` | bo | Restore GCB/TSCB from file and freeze |  | all |
| `adc_cal:save` | bo | Save calibration coefficients to file |  | all |
| `adc_cal:status` | waveform | Result of the last calibration action |  | all |

### Telemetry (LBL208)

| PV | Type | Description | Units | IOCs |
|---|---|---|---|---|
| `pmbus:chassis_fan_speed_{i}` | ao | Chassis fan {i} speed setpoint | RPM | `AlsLlrfLBL208` |
| `pmbus:chassis_fan_speed_{i}:RBV` | ai | Chassis fan {i} speed | RPM | `AlsLlrfLBL208` |
| `pmbus:psu_duty_cycle` | ai | Power supply fan duty cycle | % | `AlsLlrfLBL208` |
| `pmbus:psu_fan_speed_1` | ai | Power supply fan 1 speed | rpm | `AlsLlrfLBL208` |
| `pmbus:psu_fan_speed_2` | ai | Power supply fan 2 speed | rpm | `AlsLlrfLBL208` |
| `pmbus:psu_fan_speed_3` | ai | Power supply fan 3 speed | rpm | `AlsLlrfLBL208` |
| `pmbus:psu_fan_speed_4` | ai | Power supply fan 4 speed | rpm | `AlsLlrfLBL208` |
| `pmbus:psu_frequency` | ai | Power supply AC input frequency | Hz | `AlsLlrfLBL208` |
| `pmbus:psu_iin` | ai | Power supply AC input current | A | `AlsLlrfLBL208` |
| `pmbus:psu_iout` | ai | Power supply output current | A | `AlsLlrfLBL208` |
| `pmbus:psu_pin` | ai | Power supply input power | W | `AlsLlrfLBL208` |
| `pmbus:psu_pout` | ai | Power supply output power | W | `AlsLlrfLBL208` |
| `pmbus:psu_status` | mbbi | Power supply status word |  | `AlsLlrfLBL208` |
| `pmbus:psu_temperature_1` | ai | Power supply temperature 1 | °C | `AlsLlrfLBL208` |
| `pmbus:psu_temperature_2` | ai | Power supply temperature 2 | °C | `AlsLlrfLBL208` |
| `pmbus:psu_temperature_3` | ai | Power supply temperature 3 | °C | `AlsLlrfLBL208` |
| `pmbus:psu_vcap` | ai | Power supply bulk capacitor voltage | V | `AlsLlrfLBL208` |
| `pmbus:psu_vin` | ai | Power supply AC input voltage | V | `AlsLlrfLBL208` |
| `pmbus:psu_vout` | ai | Power supply output voltage | V | `AlsLlrfLBL208` |

<!-- END GENERATED PV TABLES -->
