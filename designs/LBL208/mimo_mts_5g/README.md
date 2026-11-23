# LBL208 mimo_mts_5g overlay

The ZCU208 `mimo_mts_5g` overlay (`designs/ZCU208/mimo_mts_5g`, design notes in `doc/wave_gen.md`) built for the
LBL208: same block design script, RTL and Makefile, with `BOARD = lbl208` and the LBL208 constraints (PL_SYSREF input
delay 0.381 ns shorter, as in the other LBL208 overlays). The analog front end is controlled through
`frontend_control_axi` (`ol.ffe`, `mimo_mts/drivers/frontend_control.py`), as in `als_llrf_mts`.

- 8 ADC and 8 DAC at 5 GSPS, MTS, one waveform generator per DAC (single, loop, CW), banked 8.2 µs captures
- CLK104A: `LMK04828_500M_CLKin0_DIST.tcs`, `LMX2594_5G.tcs` (configuration `MIMO_5G_LBL208`)
- IOC: `sudo -E mimo-5g-lbl208-ioc` (the LBL208 runs the ZCU208 PYNQ image, so `BOARD` is `ZCU208`)

    cd designs/LBL208/mimo_mts_5g && make all
