import numpy as np
import sys
from os import path
import time

from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal, QTimer, QThread, QThreadPool, QRunnable
from PyQt5.uic import loadUiType
from PyQt5.QtCore import QDateTime
import pyqtgraph as pg
import pydm

import config
from svd_widgets import Svd_stripchart
from workers import FitWfWorker, WorkerSignal_ndarray, WorkerSignal_dict


Ui_MainWindow, QMainWindow = loadUiType('main.ui')

# class svd_interface(QWidget, Ui_MainWindow): # if using pyqt instead of pydm
#     def __init__(self):
#         super(svd_interface, self).__init__()
#         self.setupUi(self)

class svd_interface(pydm.Display):
    displaySignal = pyqtSignal(dict)
    def __init__(self, parent=None, args=None, macros=None):
        self.threadpool = QThreadPool(maxThreadCount=12) # should be before super.__init__. Why?
        print('Threadpool with {} threads.'.format(self.threadpool.maxThreadCount()))
        
        super(svd_interface, self).__init__(parent=parent, args=args, macros=macros)

        # for l in self.__dir__():
        #     if 'waveform' in l:
        #     print(l)

        self._ana_count = 0
        
        # Signals for workers (multitreading)
        self.newDataSignal = WorkerSignal_ndarray()
        self.newFitSignal = WorkerSignal_dict()

        # connect stuff together
        self.waveformGraph.connect_attr('newDataSignal', self.newDataSignal)
        self.regressorWidget.connect_attr('graph', self.waveformGraph)

        # Setup the analysis timer
        self.timer = QTimer(interval=int(1/config.RATE*1000)) # timer in ms
        self.timer.timeout.connect(self.waveformGraph.get_data)
        self.timer.start()
        
        # Processing
        self.newDataSignal.signal.connect(self.fit_data)
        self.newFitSignal.signal.connect(self.trigger_display)

        # Stripcharts
        self.stripchartsView.make_stripcharts(2, useRemote=False)
        self.stripcharts = Svd_stripchart(stripchartsView=self.stripchartsView)
        self.regressorWidget.newRegressorSignal.connect(self.stripcharts.make_ravgs)
        self.newFitSignal.signal.connect(self.stripcharts.update_ravgs)
        # self.timer.timeout.connect(self.stripchartsView.update_test)

        # Update display
        self.displaySignal.connect(self.waveformGraph.display_data_fit)
        self.displaySignal.connect(self.stripcharts.update_stripchartsView)

        return

    def ui_filename(self):
        return 'main.ui'

    def ui_filepath(self):
        return path.join(path.dirname(path.realpath(__file__)), self.ui_filename())
    
    @pyqtSlot(np.ndarray)
    def fit_data(self, data):
        self.worker = FitWfWorker(
            data=data,
            roi=self.waveformGraph.get_roi(),
            regressor=self.regressorWidget.regressor,
            signal=self.newFitSignal)
        self.threadpool.tryStart(self.worker)
        return

    @pyqtSlot(dict)
    def trigger_display(self, data_dict):
        if self._ana_count<config.DISPLAY_RATE_RATIO:
            self._ana_count+=1
        else:
            self._ana_count=0
            self.displaySignal.emit(data_dict)

        
    
    # def make_stripchart(self, n=0, ts_len=100, alpha=None, n_pulse=1):
    #     self.stripcharts = Svd_stripchart(
    #         n=n, ts_len=ts_len, alpha=alpha, n_pulse=n_pulse, stripchartsView=self.stripchartsView)
    #     return

    def print_time(self):
        time = QDateTime.currentDateTime()
        print(time.toString('yyyy-MM-dd hh:mm:ss dddd'))
        return


# if __name__ == '__main__':
#     app = QApplication(sys.argv)
#     thisapp = svd_interface()
#     thisapp.show()
#     sys.exit(app.exec_())