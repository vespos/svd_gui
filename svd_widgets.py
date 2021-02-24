import numpy as np
import sys
from epics import PV
import matplotlib.pyplot as plt
from datetime import datetime

from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal, QTimer, QThread, QThreadPool, QRunnable
from PyQt5.QtWidgets import QFileDialog
from PyQt5.uic import loadUiType
import pyqtgraph as pg
import pydm

import config
import utils
from workers import GetWfWorker

sys.path.append('/reg/neh/home/espov/python/data_processing/waveform_analysis/')
import svd_waveform_processing as proc

# test data
fdata = config.TEST_DATA_FILE
test_data = np.loadtxt(fdata, delimiter=',')


# UIs
Ui_waveformGraph, QWaveformGraph = loadUiType('waveformGraph.ui')
Ui_regressor, QRegressor = loadUiType('regressor.ui')
Ui_stripchart, QStripchart = loadUiType('stripchart.ui')

class WaveformGraphWidget(QWaveformGraph, Ui_waveformGraph):
    newBkgSignal = pyqtSignal()
    def __init__(self, parent=None):
        """ Notes:
        Needs a newDataSignal to be defined from the parent using self.connect_attr
        """
        super(WaveformGraphWidget, self).__init__(parent=parent) # passing parent here is important so that widget is properly displayed in parent widget.
        self.setupUi(self)

        try:
            self.threadpool = self.parent().threadpool
        except AttributeError:
            self.threadpool = QThreadPool(maxThreadCount=4)
            print('Threadpool with {} threads started.'.format(self.threadpool.maxThreadCount()))
        
        # epics PV setup
        self.pv = PV(config.DEFAULT_CHANNEL)
        self.channelEdit.setText(config.DEFAULT_CHANNEL)
        self.channelEdit.returnPressed.connect(self.change_pv)

        # graph (using remote lead to problems with QObjects (cant be pickled))
        self.wfPlot = pg.PlotWidget()
        self.pgLayout.addWidget(self.wfPlot)
        self.wfCurve = utils.initialize_line_plot(self.wfPlot, color=config.COLORS[0])
        self.wfFit = utils.initialize_line_plot(self.wfPlot, color=config.COLORS[1])
        # self.view = pg.widgets.RemoteGraphicsView.RemoteGraphicsView()
        # self.wfPlot = self.view.pg.PlotItem()
        # self.pgLayout.addWidget(self.view)
        self.lr = pg.LinearRegionItem([0,100])
        self.lr.setZValue(-10)
        self.wfPlot.addItem(self.lr)
        self.lr.sigRegionChangeFinished.connect(self.get_roi)
        
        # background function
        self.new_bkg()
        self.bkgEdit.returnPressed.connect(self.new_bkg)
        return
    
    def connect_attr(self, name, attr):
        setattr(self, name, attr)
        return
    
    @pyqtSlot()
    def change_pv(self):
        self.pv = PV(self.channelEdit.text())
        return
    
    @pyqtSlot()
    def get_roi(self):
        self.roi = np.round(self.lr.getRegion()).astype(int)
        return self.roi
    
    @pyqtSlot()
    def get_data(self):
        self.worker = GetWfWorker(self.pv, bkg_fun=self.bkg_fun, signal=self.newDataSignal)
        self.threadpool.tryStart(self.worker) # skip (no queuing) if no thread available (if rate is too high)
        # self.worker.signals.signal.connect(self.display_data)
        return
    
    @pyqtSlot(dict)
    def display_data_fit(self, data_dict):
        data = data_dict['data']
        fit = data_dict['fit']
        # print(data.shape)
        self.wfCurve.setData(data[0],data[1])
        # self.wfPlot.plot(data[0],data[1], clear=True)
        if fit is not None:
            self.wfFit.setData(fit[0], fit[1])
        return

    @pyqtSlot()
    def new_bkg(self):
        bkg_idx = int(self.bkgEdit.text())
        if (bkg_idx<=0) or (bkg_idx is None):
            self.bkg_fun = lambda wf: 0
            print('Background subtraction removed.')
        else:
            self.bkg_fun = lambda wf: utils.background(wf, bkg_idx=bkg_idx)
            print('Background subtraction updated.')
        self.newBkgSignal.emit()
        return



class RegressorWidget(QRegressor, Ui_regressor):
    newRegressorSignal = pyqtSignal(int)
    def __init__(self, parent=None):
        super(RegressorWidget, self).__init__(parent=parent)
        self.setupUi(self)
        
        self.graph = None # to be connected in main
        self.regressor = None
        self.ref_wfs = test_data*config.POLARITY
        
        # plot
        self.basisPlot = self.basisCanvas.addPlot()
        self.basisPlot.addLegend(offset=(60,5))
        
        # connections
        self.setRegressor.clicked.connect(self.make_regressor)
        self.newrefs.clicked.connect(self.save_data)
        self.basisfile.clicked.connect(self.load_basis_file)
        return
    
    def connect_attr(self, name, attr):
        setattr(self, name, attr)
        return
    
    @pyqtSlot()
    def make_regressor(self):
        self.n_c = self.nComponents_spin.value()
        self.n_p = self.nPulses_spin.value()
        roi = self.graph.get_roi()
        try:
            delay = self.delay_txt.text()
            delay = list(map(int, delay.split(',')))
        except (TypeError, ValueError):
            delay = None
        ref_wfs = self.ref_wfs.copy()
    
        if self.graph.bkg_fun is not None:
            bkg = np.asarray([self.graph.bkg_fun(wf) for wf in ref_wfs])
            ref_wfs = (self.ref_wfs.T-bkg).T
        if roi is None:
            print('Roi not defined, entire waveform taken.')
        else:
            ref_wfs = ref_wfs[:,roi[0]:roi[1]]
        regr = proc.construct_waveformRegressor(
                                            ref_wfs, 
                                            n_components=self.n_c, 
                                            n_pulse=self.n_p, 
                                            delay=delay
                                            )
        self.regressor = regr
        self.show_basis()
        self.newRegressorSignal.emit(regr.n_pulse_)
        print('Regressor updated. Shape of basis: {}.'.format(regr.A.shape))
        return
    
    def show_basis(self):
        A = self.regressor.A
        self.basisPlot.clear()
        basisData = []
        cmap = plt.cm.viridis(np.linspace(0.25,0.95,A.shape[0]))*255 # mpl is 0-1, pg is 0-255
        cmap = cmap.astype(int)
        for ii, a in enumerate(A):
            basisData.append(self.basisPlot.plot(a/2**ii, pen=pg.mkPen(color=cmap[ii], width=1),
                                                 name='base {}'.format(ii)))
        return
    
    @pyqtSlot()
    def save_data(self):
        print('Start saving new set of reference waveforms...')
        self._save_count = 0
        self._to_be_saved = []
        self.graph.newDataSignal.signal.connect(self._save_data)
        return
    
    @pyqtSlot(np.ndarray)
    def _save_data(self, data):
        self._to_be_saved.append(data[1])
        self._save_count+=1
        if self._save_count>=config.SAVE_NUMBER:
            self.graph.newDataSignal.signal.disconnect(self._save_data)
            to_be_saved = np.asarray(self._to_be_saved)
            fname = './refs/refs_{}.npy'.format(datetime.now().isoformat().replace(':','_')[:-7])
            np.save(fname, to_be_saved)
            self._to_be_saved = None
            print('{} reference waveforms saved to {}.'.format(self._save_count,fname))
        return

    @pyqtSlot()
    def load_basis_file(self):
        dlg = QFileDialog()
        dlg.setFileMode(QFileDialog.AnyFile)
        # dlg.setFilter("Text files (*.txt)")
        # filename = QStringList()
		
        if dlg.exec_():
            filename = dlg.selectedFiles()
            self.ref_wfs = np.load(filename[0])*config.POLARITY
            print('Reference waveforms loaded.')
        return



class StripchartsView(Ui_stripchart, QStripchart):
    """ Generic widget to plot a number of stricharts.
    """
    def __init__(self, parent=None):
        super(StripchartsView, self).__init__(parent=parent)
        self.setupUi(self)
        return

    def make_stripcharts(self, n, useRemote=False):
        """ Initialize a number of stripcharts in the layout. Should really only be called once when
        the widget is created.
        Args:
            n (int): number of stripcharts.
            useRemote (bool): use RemoteGraphicsView. Should improve performance (although it
                does not seem to...)
        """
        self.stripcharts = []
        for ii in range(n):
            if useRemote:
                view = pg.widgets.RemoteGraphicsView.RemoteGraphicsView()
                stripchart = view.pg.PlotItem()
                stripchart._setProxyOptions(deferGetattr=True)  ## speeds up access to plot
                view.setCentralItem(stripchart)
                self.stripchartsLayout.addWidget(view, row=ii, col=1, rowspan=1, colspan=1)
            else:
                stripchart = pg.PlotWidget() # pyqtGraph plot widget
                # stripchart = pydm.widgets.timeplot.PyDMTimePlot() # pydmTimePlot
                self.stripchartsLayout.addWidget(stripchart, row=ii, col=1, rowspan=1, colspan=1)
            self.stripcharts.append(stripchart)
        print('{} stripcharts initialized.'.format(n))
        return
    
    def make_stripchartsData(self, N):
        """ Initialize a number of curves for each stripcharts. Can be used to reset the data.
        Args:
            N (tuple): number of curves in each stripcharts.
        """
        assert len(N)==len(self.stripcharts), 'len(N) does not match number of stricharts.'
        self.clear_stripcharts()
        self.stripchartsData = []
        for ii,n in enumerate(N):
            for jj in range(n):
                self.stripchartsData.append(
                    utils.initialize_line_plot(self.stripcharts[ii], config.COLORS[jj])
                    )
        return

    def clear_stripcharts(self):
        for stripchart in self.stripcharts:
            for item in stripchart.listDataItems():
                stripchart.removeItem(item)
        return

    
    def update(self, stripchartsData):
        for data, dataObj in zip(stripchartsData, self.stripchartsData):
            dataObj.setData(data)
        return

    def update_test(self):
        """ For testing purposes only. Initialize a (2,1) or (2,2) stripchart. """
        N = 1000
        data = np.random.normal(size=(N,50)).sum(axis=1)
        data += 5 * np.sin(np.linspace(0, 10, data.shape[0]))
        data1 = 0.1*np.random.normal(size=(N,50)).sum(axis=1)
        data1 += 10 * np.sin(np.linspace(0, 10, data.shape[0]))
        self.stripchartsData[0].setData(data)
        self.stripchartsData[1].setData(data1)
        self.stripchartsData[2].setData(data)
        # self.stripchartsData[3].setData(data1)
        # data = [data]
        return


class Svd_stripchart(QObject):
    """ Class to handle running average of svd fit results.
    Needs a two stripcharts view.
    In the first stripchart holds the score stripchart and the second 
    stripchart the pulses intensities.
    """
    def __init__(self, n=0, ts_len=1000, alpha=None, n_pulse=1, stripchartsView=None):
        super(Svd_stripchart, self).__init__()
        self.n = n
        self.ts_len = ts_len
        self.alpha = alpha
        self.n_pulse = n_pulse
        self.stripchartsView = stripchartsView
        self._ravg_ready = False

        self.stripchartsView.NEdit.returnPressed.connect(self.update_ravg_parameters)
        self.stripchartsView.movAvEdit.returnPressed.connect(self.update_ravg_parameters)
        return

    def connect_attr(self, name, attr):
        setattr(self, name, attr)
        return

    @pyqtSlot()
    def update_ravg_parameters(self):
        self.ts_len = int(self.stripchartsView.NEdit.text())
        self.n = int(self.stripchartsView.movAvEdit.text())
        self.make_ravgs(self.n_pulse)
        # if self._ravg_ready:
        return
    
    @pyqtSlot(int)
    def make_ravgs(self, n_pulse):
        """ Instantiate running averages
        """
        self.n_pulse = n_pulse
        self.ravg_score = utils.RunningAverage(self.n, self.ts_len, alpha=self.alpha)
        self.ravg_int = []
        for ii in range(n_pulse):
            self.ravg_int.append(utils.RunningAverage(self.n, self.ts_len, alpha=self.alpha))
        self.stripchartsView.make_stripchartsData((1,len(self.ravg_int)))
        self._ravg_ready = True
        print('Stripchart 1: fit score\nStripchart 2: {} pulses intensities'.format(self.n_pulse))
        return
    
    @pyqtSlot(dict)
    def update_ravgs(self, data_dict):
        if not self._ravg_ready:
            return
        # print(data_dict['intensity'])
        self.ravg_score.update_ravg_ts(data_dict['score'])
        for ii,ravg in enumerate(self.ravg_int):
            ravg.update_ravg_ts(data_dict['intensity'][ii])
        return
    
    @pyqtSlot(dict)
    def update_stripchartsView(self, data_dict):
        if not self._ravg_ready:
            return
        data = self.get_stripchartsData()
        self.stripchartsView.update(data)
        return
    
    def get_stripchartsData(self):
        data = [self.ravg_score.ravg_ts]
        for ii,ravg in enumerate(self.ravg_int):
            data.append(ravg.ravg_ts)
        return data
