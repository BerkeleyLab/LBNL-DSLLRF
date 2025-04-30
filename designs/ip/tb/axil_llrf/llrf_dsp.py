import numpy as np


class LLRFModule:
    def __init__(self, width: int = 16) -> None:
        """Base class for LLRF DSP module

        Args:
            width (int): datawidth of the module. Defaults to 16.
        """
        self.width = width
        self._gain = 1
        self._submodules = []

    @property
    def gain(self):
        return self._gain

    @gain.setter
    def gain(self, val) -> None:
        self._gain = val

    @property
    def submodules(self) -> list:
        return self._submodules

    @submodules.setter
    def submodules(self, val) -> None:
        self._submodules = val
        self._gain = 1
        for m in val:
            self._gain *= m.gain

    def __repr__(self):
        str = (f"< {self.__class__.__name__:12s}:   "
               f"Amp gain={np.abs(self.gain):6.3f},   "
               f"Phs gain={np.angle(self.gain, deg=True):8.2f} deg >\n")
        for m in self.submodules:
            str += (f"{m.__class__.__name__:14s}:   "
                    f"Amp gain={np.abs(m.gain):6.3f},   "
                    f"Phs gain={np.angle(m.gain, deg=True):8.2f} deg;\n")
        return str


class CORDIC(LLRFModule):
    CORDIC_GAIN = 1.646760258

    def __init__(self, width: int = 22,
                 pipeline_delay: int = 22,
                 phase_off_deg: float = 0) -> None:
        """Receiver or Transceiver CORDIC.
            Gateware: cordicg_b22.v (rx_cordic or tx_cordic).

        Args:
            width (int): internal datawidth of the module. Defaults to 22.
            pipeline_delay (int): nstg-1 of the module. Defaults to 20.
            phase_off_deg (float): Phase offset in degrees.
        """
        super().__init__(width)
        self.pipeline_delay = pipeline_delay
        self.gain = self.CORDIC_GAIN * np.exp(1j * np.deg2rad(phase_off_deg))


class Coupler(LLRFModule):
    def __init__(self, input_width: int = 16,
                 output_width: int = 18,
                 pipeline_delay: int = 1) -> None:
        """Receiver / Transmitter coupler to pad signal datawitdh
            between axi stream and dsp_core.
        Args:
            input_width (int): input datawidth of the module. Defaults to 16.
            output_width (int): output datawidth of the module. Defaults to 18.
        """
        super().__init__(input_width)
        self.gain = 2 ** (output_width - input_width)
        self.pipeline_delay = pipeline_delay


class LLRFModel(LLRFModule):
    def __init__(self, width: int = 18,
                 input_width: int = 16,
                 output_width: int = 16) -> None:
        """DSP chain in llrf_dsp.v.
        Args:
            width (int): datawidth of the dsp_core. Defaults to 16.
            input_width (int): input datawidth of the module. Defaults to 18.
            output_width (int): output datawidth of the module. Defaults to 18.
        """
        super().__init__(width)

        self.rx_coupler = Coupler(input_width=input_width,
                                  output_width=width)
        self.rx_cordic = CORDIC(phase_off_deg=0)
        self.tx_cordic = CORDIC(phase_off_deg=0)
        self.tx_coupler = Coupler(input_width=width,
                                  output_width=output_width)

        self.rx_gain = self.rx_coupler.gain * self.rx_cordic.gain
        self.tx_gain = self.tx_coupler.gain * self.tx_cordic.gain
        self.submodules += [
            self.rx_coupler,
            self.rx_cordic,
            self.tx_cordic,
            self.tx_coupler]
        self.max_adc_amp = (1 << (self.width-1)) / np.abs(self.rx_gain) * 0.99

    def calc_open_loop_setp(self, amp_setpoint_adc, phs_setpoint_deg):
        """calculate open loop setpoint register values

        Args:
            amp_setpoint_adc (float): amplitude loop setpoint in ADC counts.
            phs_setpoint_deg (float): phase loop setpoint in degrees.

        Returns:
            amplitude and phase loop setpoint values in ADC counts
        """
        # scaling to compensate open loop setpoint (after PID)
        amp_setpoint = amp_setpoint_adc / np.abs(self.tx_gain)
        phs_setpoint = phs_setpoint_deg / 360 * (1 << self.width)
        return int(amp_setpoint), int(phs_setpoint)

    def calc_close_loop_setp(self, amp_setpoint_adc, phs_setpoint_deg):
        """calculate close loop setpoint register values

        Args:
            amp_setpoint_adc (float): amplitude loop setpoint in ADC counts.
            phs_setpoint_deg (float): phase loop setpoint in degrees.
        Returns:
            amplitude and phase loop setpoint values in ADC counts
        """
        # signal gain for open loop setpoint (before PID)
        amp_setpoint = amp_setpoint_adc * np.abs(self.rx_gain)
        phs_setpoint = phs_setpoint_deg / 360 * (1 << self.width)
        return int(amp_setpoint), int(phs_setpoint)


if __name__ == "__main__":
    llrf = LLRFModel()
    print(llrf)
    print(f"RX Gain: {llrf.rx.gain}")
    print(f"TX Gain: {llrf.tx.gain}")
