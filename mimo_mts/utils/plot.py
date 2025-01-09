from scipy import signal
import numpy as np
import matplotlib.pyplot as plt

plt.rcParams['figure.figsize'] = [8, 5]
plt.rcParams['axes.grid'] = True
plt.rcParams['axes.grid.which'] = "both"
plt.rcParams['grid.linewidth'] = 0.5
plt.rcParams['grid.alpha'] = 0.5
plt.rcParams['font.size'] = 8


def plot_adc_wfm(cdata, fs=4e9, width=8, height=1):
    fs /= 1e9
    n_ch, n_samples = cdata.shape
    t = np.arange(0, n_samples/fs, 1/fs)
    fig, axes = plt.subplots(
        n_ch, sharex=True, figsize=(width, n_ch*height))
    for i, (wfm, ax) in enumerate(zip(cdata, axes)):
        ax.plot(t, wfm, label=f'chan {i} ')
        # ax.set_title(f'chan {i} ')
        ax.legend()
        ax.set_xlabel('Time [ns]')


def plot_adc_psd(wfm, fs=4e9, onsided=True, width=8, height=2):
    f, pxxs = signal.periodogram(
        wfm, fs, 'flattop', scaling='spectrum',
        return_onesided=onsided)
    if not onsided:
        f = np.fft.fftshift(f)
        pxxs = np.fft.fftshift(pxxs, axes=1)
    n_ch, n_samples = wfm.shape
    fig, axes = plt.subplots(
        n_ch, sharex=True, figsize=(width, n_ch*height))
    for i, (pxx, ax) in enumerate(zip(pxxs, axes)):
        f_peak = f[np.argmax(pxx)]
        ax.plot(f, 10*np.log10(pxx), label=f'ADC {i}, peak: {f_peak/1e6:.3f} MHz')
        # ax.set_title(f'ADC {i}, peak: {f_peak/1e6:.3f} MHz ')
        ax.legend()
        ax.set_xlabel('Freq [MHz]')
        ax.set_ylabel('Power [dBFS]')