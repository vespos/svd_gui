import  numpy as np
from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal, QTimer, QThread, QThreadPool, QRunnable

import config


class WorkerSignal(QObject):
    """ This is a hack to be able to send signals from a QRunnable instance. 
    For some reason, it is impossible to inherit from both QObject and QRunnable 
    in Python (it is in C++)...
    """
    signal = pyqtSignal()

class WorkerSignal_str(QObject):
    signal = pyqtSignal(str)

class WorkerSignal_int(QObject):
    signal = pyqtSignal(int)

class WorkerSignal_ndarray(QObject):
    signal = pyqtSignal(np.ndarray)

class WorkerSignal_dict(QObject):
    signal = pyqtSignal(dict)


class Worker(QRunnable):
    """ Generic Task for ThreadPool to execute required Kwargs =
    target (<function>): function to call
    args  (tuple): args for target
    kwargs (dict): kwargs for target 
    signal: Instance of one of the WorkerSignal_*, matching the output of the target function
    """  
    def __init__(self, target=None, args=(), kwargs={}, signal=None):
        super(Worker, self).__init__()
        self.target = target 
        self.args = args
        self.kwargs = kwargs

        self.signals = WorkerSignal()
        types = ['str','int','ndarray']
        for t in type:
            if type_out==t:
                self.signals = eval('Workersignal_{}()'.format(t))

    def run(self):
        out = self.target(*self.args, **self.kwargs)
        self.signals.signal.emit(out)


class GetWfWorker(QRunnable):
    '''
    Worker thread to get data from a PV instance.
    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.
    '''
    def __init__(self, pv, bkg_fun=None, signal=None):
        """ Args:
        pv: pv instance
        bkg_fun: function to calculate the background. Must take wf as single input.
        signal: WorkerSignal instance to be emitted when data is available
        """
        super(GetWfWorker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.pv = pv
        self.bkg_fun = bkg_fun
        # Add the callback to our kwargs
        # self.kwargs['progress_callback'] = self.signals.progress
        
        # Signal (this is a hack to be able to send signals from a QRunnable instance)
#         self.signals = WorkerSignal_ndarray()
        self.signals = signal
        return
    
    @pyqtSlot()
    def run(self):
        '''
        Initialise the runner function with passed args, kwargs.
        '''
        data = self.pv.get_with_metadata()
        y = data['value']
        x = np.arange(y.size) # just to get some x-values
        if self.bkg_fun is not None:
            y = y-self.bkg_fun(y)
        d = np.c_[x,y].T
        # d = data['value']
        if self.signals is not None:
            self.signals.signal.emit(d)
        return


class FitWfWorker(QRunnable):
    '''
    Worker thread to get data from a PV instance.
    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.
    '''
    def __init__(self, data=None, roi=None, regressor=None, signal=None):
        """ Args:
        data: data to fit
        roi: roi
        regressor: regressor instance
        signal: WorkerSignal instance to be emitted when fit is done
        """
        super(FitWfWorker, self).__init__()

        self.data = data
        self.roi = roi
        self.regressor = regressor
        self.signals = signal
        self._polarity = config.POLARITY
        return
    
    @pyqtSlot()
    def run(self):
        dat_fit = self.data[1]*self._polarity
        if self.roi is not None:
            dat_fit = dat_fit[self.roi[0]:self.roi[1]]
            xfit = np.arange(self.roi[0],self.roi[1])
        else:
            xfit = np.arange(dat_fit.size)
        if self.regressor is not None:
            fit, score = self.regressor.fit_reconstruct(dat_fit, return_score=True)
            fit = np.squeeze(fit)*self._polarity
            fit = np.c_[xfit,fit].T
            intensity = self.regressor.get_pulse_intensity(dat_fit, mode=config.INTENSITY_MODE)
            intensity = intensity[0]
        else:
            fit = None
            intensity = 0
            score = 0

        data_dict = {
            'score': score,
            'intensity': intensity,
            'fit': fit,
            'data': self.data
        }
        if self.signals is not None:
            self.signals.signal.emit(data_dict)