import numpy as np
from collections import deque
from PyQt5.QtCore import QObject, pyqtSignal, QRunnable
import pyqtgraph as pg


"""
#################################################################
#################### Generic pyQt utilities #####################
#################################################################
"""

def initialize_line_plot(plotObj, color):
    x = [0]
    y = [0]
    # dataObj = plotObj.plot(x,y, pen=pg.mkPen(color, width=2))
    # dataObj = plotObj.plot(x,y, pen={'color':color, 'width':2})
    dataObj = plotObj.plot(x,y, pen=color)
    return dataObj

    
"""
#################################################################
############## Analysis functions and other tools ###############
#################################################################
"""
def background(signal, bkg_idx=100):
    """
    Return background value
    """
    return np.median(signal[0:bkg_idx])


class RunningAverage(object):
    """
    Class to handle a running average of data and a time series of the running average
    """
    def __init__(self, n, ts_len, alpha=None):
        """
        Args:
            n: n-moving average
            ts_len: length of the running average time series
            alpha: exponential average parameter. If None, linear average of length n is performed.
        """
        self.n = n
        self.ts_len = ts_len
        self.alpha = alpha
        self.ravg = 0
        self.ravg_ts = np.array([])
        return

    def update_ravg(self, newDataPoint):
        """
        Update self.ravg only
        """
        if self.alpha is None:
            self.ravg = (newDataPoint+self.n*self.ravg)/(self.n+1)
        else:
            self.ravg = self.alpha*newDataPoint + (1-self.alpha)*self.ravg
        return
    
    def update_ravg_ts(self, newDataPoint, needx=False):
        """ 
        Update self.ravg and self.ravg_ts
        needx: in case dummy x coordinates are needed for plotting
        """
        self.update_ravg(newDataPoint)
        self.ravg_ts = np.append(self.ravg_ts, self.ravg)
        if self.ravg_ts.shape[0]>self.ts_len:
            self.ravg_ts = self.ravg_ts[-self.ts_len:]
        if needx:
            self.ravg_tsx = np.arange(self.ravg_ts.size)
        return