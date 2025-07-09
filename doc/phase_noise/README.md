# Phase Noise Measurements

All preliminary phase noise measurements (absolute and additive) were performed using [R&S FSWP Phase noise analyzer](https://www.rohde-schwarz.com/us/products/test-and-measurement/phase-noise-analyzers/rs-fswp-phase-noise-analyzer-and-vco-tester_63493-120512.html). Data analysis, including plotting and RMS jitter calculations, was carried out using Jupyter notebooks.

Notebooks:
- Original (og): Measurements  with jitter cleaner PLLs (LMK04848) - [phase_noise_plot.ipynb](doc/phase_noise/phase_noise_plot_og.ipynb)
- Distributed mode LMK04828 (option3): Measuremnets with and without modified LMX2594 - [phase_noise_plot_option3.ipynb](doc/phase_noise/phase_noise_plot_option3.ipynb)

LMX2594 loop filter was optimized using [Simulations](doc/phase_noise/data/lmx_simulations) performed with Texas Instruments PLLatinum Simulator Tool [PLLATINUMSIM-SW](https://www.ti.com/tool/PLLATINUMSIM-SW).

All raw measurement data and screenshots from the FSWP instrument are stored in the [data](doc/phase_noise/data) directory. Data is organized by experiment: ["og" (original)](doc/phase_noise/data/og) or ["option3" (distributed mode)](doc/phase_noise/data/option3), each accompanied by the corresponding block diagram of the measurement setup.
