import time
import asyncio
import argparse
from mimo_mts.overlay import MimoMtsOverlay


async def wait_for_irq(ol):
    irq = ol.write_done_irq
    t0 = time.perf_counter()
    while True:
        await irq.wait()
        t1 = time.perf_counter()
        adc_i, adc_q = ol.capture_adc_iq_buf()
        adc_c = adc_i + 1j * adc_q
        print(f"IRQ!, time since last: {t1-t0:.6f} s, adc_c:{adc_c.shape}")
        t0 = t1


def main():
    parser = argparse.ArgumentParser(description='Test MIMO MTS Overlay')
    parser.add_argument('--config', default='ALS_LLRF_ZCU208', help='Overlay configuration')
    parser.add_argument('--trig_period', type=float, default=25e6, help='Trigger period in dsp_clk cycles')
    args = parser.parse_args()

    dsp_clk_mhz = 250  # dsp_clk
    trig_period = args.trig_period

    print(f"dsp_clk_mhz: {dsp_clk_mhz} MHz")
    print(f"trigger frequency: {dsp_clk_mhz * 1e6 / trig_period:.2f} Hz")

    ol = MimoMtsOverlay(config='ALS_LLRF_ZCU208', download=True)

    # setup internal trigger
    ol.rf_control.register_map.trig_period = trig_period
    ol.rf_control.register_map.trig_sel = 0
    ol.rf_control.register_map.trig_delay = 0
    ol.rf_control.register_map.trig_divide = 1
    ol.rf_control.register_map.dac_enable = 1
    ol.rf_control.register_map.pulse_length = 0xfff

    loop = asyncio.get_event_loop()
    task = loop.create_task(wait_for_irq(ol))
    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        print("KeyboardInterrupt received. Stopping the loop.")
        task.cancel()
    finally:
        loop.close()


if __name__ == "__main__":
    main()
