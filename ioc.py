from mimo_mts import MimoMtsOverlay
import numpy as np
import argparse
from softioc import softioc, builder, asyncio_dispatcher
import asyncio


class MimoMtsIoc:
    def __init__(self, **kwargs) -> None:
        self.prefix = kwargs.get('prefix', 'MIMO:MTS')
        self.ioc_name = 'linac-llrf'
        self.ol_config = kwargs.get('ol_config', 'MIMO_ZCU208')

    def __enter__(self):
        self.ol = MimoMtsOverlay(config=self.ol_config)
        print(self.ol)
        self.init_rf_control()
        self.adc_bufs_i, self.adc_bufs_q = self.ol.capture_adc_iq_buf()
        self.adc_bufs_c = self.adc_bufs_i + 1j * self.adc_bufs_q
        self.adc_bufs_mean = self.adc_bufs_c.reshape(8, -1, 8).mean(axis=2)
        self.n_adc, self.n_samples = self.adc_bufs_c.shape
        self.fs_ghz = self.ol.board.adc_sampling_rate / 1e9
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def init_rf_control(self):
        self.ol.rf_control.register_map.trig_period = 250e6
        self.ol.rf_control.register_map.trig_sel = 0
        self.ol.rf_control.register_map.trig_delay = 0
        self.ol.rf_control.register_map.trig_divide = 1
        self.ol.rf_control.register_map.dac_enable = 1
        self.ol.rf_control.register_map.pulse_length = 0xfff

    def update_adc_bufs(self):
        self.ol.capture_adc_iq_buf(self.adc_bufs_i, self.adc_bufs_q)
        self.adc_bufs_c = self.adc_bufs_i + 1j * self.adc_bufs_q
        self.adc_bufs_mean = self.adc_bufs_c.reshape(8, -1, 8).mean(axis=2)

    def create_ioc(self):
        builder.SetDeviceName(self.prefix)
        self.pvs_in = {}
        name = 'ADC:TWF'  # in ns
        self.pvs_in[name] = builder.WaveformIn(
            name, np.arange(0, self.n_samples/self.fs_ghz, 1/self.fs_ghz))
        name = 'DSP:TWF'  # in ns, decimation by 8
        self.pvs_in[name] = builder.WaveformIn(
            name, np.arange(0, self.n_samples/self.fs_ghz, 8/self.fs_ghz))
        for ix in range(self.n_adc):
            name = f'ADC{ix}:IWF'
            self.pvs_in[name] = builder.WaveformIn(name, self.adc_bufs_i[ix])
            name = f'ADC{ix}:QWF'
            self.pvs_in[name] = builder.WaveformIn(name, self.adc_bufs_q[ix])
            name = f'ADC{ix}:AWF'
            self.pvs_in[name] = builder.WaveformIn(name, np.abs(self.adc_bufs_c[ix]))
            name = f'ADC{ix}:PWF'
            self.pvs_in[name] = builder.WaveformIn(name, np.angle(self.adc_bufs_c[ix], deg=True))
            name = f'DSP:ADC{ix}:AWF'
            self.pvs_in[name] = builder.WaveformIn(name, np.abs(self.adc_bufs_mean[ix]))
            name = f'DSP:ADC{ix}:PWF'
            self.pvs_in[name] = builder.WaveformIn(name, np.angle(self.adc_bufs_mean[ix], deg=True))

    def start_ioc(self):
        dispatcher = asyncio_dispatcher.AsyncioDispatcher()
        builder.LoadDatabase()
        # softioc.devIocStats(self.ioc_name)
        # builder.dbLoadDatabase('linac_llrf.db', substitutions=f'P={self.prefix}:')
        softioc.iocInit(dispatcher)
        asyncio.run_coroutine_threadsafe(self.update(), dispatcher.loop)

    async def update(self):
        while True:
            self.update_adc_bufs()
            for ix in range(self.n_adc):
                name = f'ADC{ix}:IWF'
                self.pvs_in[name].set(self.adc_bufs_i[ix])
                name = f'ADC{ix}:QWF'
                self.pvs_in[name].set(self.adc_bufs_q[ix])
                name = f'ADC{ix}:AWF'
                self.pvs_in[name].set(np.abs(self.adc_bufs_c[ix]))
                name = f'ADC{ix}:QWF'
                self.pvs_in[name].set(np.angle(self.adc_bufs_c[ix], deg=True))
                name = f'DSP:ADC{ix}:AWF'
                self.pvs_in[name].set(np.abs(self.adc_bufs_mean[ix]))
                name = f'DSP:ADC{ix}:PWF'
                self.pvs_in[name].set(np.angle(self.adc_bufs_mean[ix], deg=True))
            await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="soft IOC")
    parser.add_argument('--prefix', default="MIMO:MTS", help="$(P)")
    parser.add_argument('--ol_config', default="MIMO_ZCU208", help="overlay config",
                        choices=['ALS_LLRF_LBL208', 'MIMO_ZCU208', 'MIMO_ZCU216'])
    args = parser.parse_args()

    with MimoMtsIoc(**vars(args)) as ioc:
        ioc.create_ioc()
        ioc.start_ioc()
        softioc.interactive_ioc(globals())


if __name__ == "__main__":
    main()
