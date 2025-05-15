from scipy import signal
import numpy as np
import matplotlib.pyplot as plt

plt.rcParams['figure.figsize'] = [8, 5]
plt.rcParams['axes.grid'] = True
plt.rcParams['axes.grid.which'] = "both"
plt.rcParams['grid.linewidth'] = 0.5
plt.rcParams['grid.alpha'] = 0.5
plt.rcParams['font.size'] = 6
plt.style.use('default')


def plot_complex_wfm(cdata, fs=4e9, width=8, height=2, mode='iq', title=''):
    fs /= 1e9
    n_samples = len(cdata)
    t = np.arange(0, n_samples/fs, 1/fs)
    fig, axes = plt.subplots(
        2, sharex=True, figsize=(width, 2*height))
    if mode == 'iq':
        axes[0].plot(t, cdata.real, label='I [cnt]')
        axes[1].plot(t, cdata.imag, label='Q [cnt]')
    elif mode == 'ap':
        axes[0].plot(t, np.abs(cdata), label='amplitude [cnt]')
        axes[1].plot(t, np.angle(cdata, deg=True), label='phase [deg]')
    axes[1].set_xlabel('Time [ns]')
    axes[0].legend()
    axes[1].legend()
    fig.tight_layout()
    fig.suptitle(title, y=1.02)


def plot_adc_wfm(cdata, fs=4e9, width=8, height=1, title=''):
    fs /= 1e9
    n_ch, n_samples = cdata.shape
    t = np.arange(0, n_samples/fs, 1/fs)
    fig, axes = plt.subplots(
        n_ch, sharex=True, figsize=(width, n_ch*height))
    for i, (wfm, ax) in enumerate(zip(cdata, axes)):
        ax.plot(t, wfm, label=f'chan {i} ')
        ax.legend()
        ax.set_xlabel('Time [ns]')
    fig.tight_layout()
    fig.suptitle(title, y=1.02)


def plot_adc_psd(wfm, fs=4e9, onsided=True, width=8, height=2, title=''):
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
        ax.plot(f, 10*np.log10(pxx),
                label=f'ADC {i}, peak: {f_peak/1e6:.3f} MHz')
        # ax.set_title(f'ADC {i}, peak: {f_peak/1e6:.3f} MHz ')
        ax.legend()
        ax.set_xlabel('Freq [MHz]')
        ax.set_ylabel('Power [dBFS]')
    fig.tight_layout()
    fig.suptitle(title, y=1.02)


def plot_complex_wfm_stack(cdata, fs=4e9, width=8, height=4, title=''):
    fs /= 1e9
    n_ch, n_samples = cdata.shape
    t = np.arange(0, n_samples/fs, 1/fs)
    fig, axes = plt.subplots(
        2, 1, sharex=True, figsize=(width, height))
    for ch, wfm in enumerate(cdata):
        axes[0].plot(t, wfm.real, label=f'ADC{ch} I')
        axes[1].plot(t, wfm.imag, label=f'ADC{ch} Q')
        axes[0].legend()
        axes[1].legend()
    axes[-1].set_xlabel('Time [ns]')
    fig.tight_layout()
    fig.suptitle(title, y=1.02)
