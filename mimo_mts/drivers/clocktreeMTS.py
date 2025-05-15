from pynq import DefaultHierarchy
import time


class ClockTreeMTS(DefaultHierarchy):
    def __init__(self, description):
        super().__init__(description)
        self.dspclk_freqcnt = self.freqcnt_gpio.channel1

    def convert_freq_to_hz(self, f_cnt, f_ref=100.0e6):
        """Convert the frequency counter value to Hz"""
        return (f_cnt / 2**24) * f_ref

    @property
    def dspclk_freq_hz(self):
        return self.convert_freq_to_hz(self.dspclk_freqcnt.read())

    def reset_mmcm(self):
        # Reset MTS ClockWizard MMCM - refer to PG065
        self.MTSclkwiz.mmio.write_reg(0, 0xA)
        time.sleep(0.1)

    def check_mmcm_locked(self):
        """ Check if MTS ClockWizard MMCM is locked """
        # reads the LOCK register
        # the ClockWizard AXILite registers are NOT fully mapped:
        # refer to PG065
        mmcm_status = self.MTSclkwiz.read(0x0004)
        return (mmcm_status & 0x1) == 0x1

    @staticmethod
    def checkhierarchy(description):
        if 'MTSclkwiz' in description['ip'] \
           and 'freqcnt_gpio' in description['ip']:
            return True
        return False
