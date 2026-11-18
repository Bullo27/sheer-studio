import os, numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.io import wavfile
from scipy import signal as sg
D=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'unity', 'Assets', 'Sheer', 'Resources', 'Audio', 'Sfx')
names=['stretch_loop','rip','zip_loop','snap','pop','tick','toggle_on','toggle_off','shutter','sparkle','achievement','boing','squeak','whoosh']
fig,ax=plt.subplots(len(names),2,figsize=(14,2.0*len(names)))
for i,n in enumerate(names):
    sr,x=wavfile.read(os.path.join(D,n+'.wav')); x=x.astype(float)/32768
    if x.ndim==2: x=x.mean(1)
    t=np.arange(len(x))/sr
    ax[i,0].plot(t,x,lw=0.4); ax[i,0].set_ylim(-1,1); ax[i,0].set_ylabel(n,fontsize=8)
    f,tt,Z=sg.spectrogram(x,sr,nperseg=256,noverlap=192)
    ax[i,1].pcolormesh(tt,f,10*np.log10(Z+1e-12),vmin=-110,vmax=-30,shading='auto',cmap='magma')
fig.tight_layout(); fig.savefig('out/sfx.png',dpi=55)
