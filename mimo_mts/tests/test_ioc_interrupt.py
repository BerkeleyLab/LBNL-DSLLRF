import argparse
import logging
from mimo_mts.ioc.app_iocs import AlsLlrfZCU208


def main():
    parser = argparse.ArgumentParser(description='Test Overlay Interrupts through IOC')
    parser.add_argument('--trig_period', type=float, default=25e6, help='Trigger period in dsp_clk cycles')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()

    dsp_clk_mhz = 250  # dsp_clk
    trig_period = args.trig_period

    print(f"dsp_clk_mhz: {dsp_clk_mhz} MHz")
    print(f"trigger frequency: {dsp_clk_mhz * 1e6 / trig_period:.2f} Hz")

    # The IOC will now handle the ISR internally using its dispatcher
    log_level = logging.DEBUG if args.debug else logging.INFO
    ioc = AlsLlrfZCU208(log_level=log_level)

    # Override trigger period from CLI
    ioc.ol.rf_control.register_map.trig_period = int(trig_period)

    ioc.run_ioc()


if __name__ == "__main__":
    main()
