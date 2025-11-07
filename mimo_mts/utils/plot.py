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


def plot_adc_psd(wfm, fs=4e9, onsided=True, fullscale=32767, width=8, height=2, title=''):
    f, pxxs = signal.periodogram(
        wfm, fs, 'flattop', scaling='spectrum',
        return_onesided=onsided)
    if not onsided:
        f = np.fft.fftshift(f)
        pxxs = np.fft.fftshift(pxxs, axes=1)
    n_ch, n_samples = wfm.shape
    fig, axes = plt.subplots(
        n_ch, sharex=True, figsize=(width, n_ch*height))
    fsdb = 20 * np.log10(fullscale / np.sqrt(2))
    pxx_dbfs = 10 * np.log10(pxxs) - fsdb
    for i, (p, ax) in enumerate(zip(pxx_dbfs, axes)):
        f_peak = f[np.argmax(p)]
        ax.plot(f, p, label=f'ADC {i}, peak: {f_peak/1e6:.3f} MHz')
        # ax.set_title(f'ADC {i}, peak: {f_peak/1e6:.3f} MHz ')
        ax.legend()
        ax.set_xlabel('Freq [MHz]')
        ax.set_ylabel('Power [dBFS]')
    fig.tight_layout()
    fig.suptitle(title, y=1.02)


def plot_complex_wfm_stack(cdata, fs=4e9, width=8, height=4, mode='iq', title='', legend=False):
    fs /= 1e9
    n_ch, n_samples = cdata.shape
    t = np.arange(0, n_samples/fs, 1/fs)
    fig, axes = plt.subplots(
        2, 1, sharex=True, figsize=(width, height))
    for ch, wfm in enumerate(cdata):
        if mode == 'iq':
            axes[0].plot(t, wfm.real, label=f'{ch}')
            axes[1].plot(t, wfm.imag, label=f'{ch}')
        elif mode == 'ap':
            axes[0].plot(t, np.abs(wfm), label=f'{ch}')
            axes[1].plot(t, np.angle(wfm, deg=True), label=f'{ch}')
    if legend:
        axes[0].legend()
        axes[1].legend()
    if mode == 'iq':
        axes[0].set_title('I [cnt]')
        axes[1].set_title('Q [cnt]')
    elif mode == 'ap':
        axes[0].set_title('Amplitude [cnt]')
        axes[1].set_title('Phase [deg]')
    axes[-1].set_xlabel('Time [ns]')
    # fig.tight_layout()
    fig.suptitle(title, y=1.02)
