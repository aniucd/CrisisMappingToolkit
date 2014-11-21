"""
A GUI to assist in quickly finding good parameters for well tested flood detection
algorithms.  It is built using tools from the core GUI file.

It consists of one large map with an inspector tool that appears when it is right clicked.
"""


'''
Goals for production GUI (Only for Google):
- Done through a new top level python script
- (Nice) Wizard to walk through setting parameters / selecting algorithms
- Parameter adjustment with fixed bank of widgets
- Simplified right click menu
- Display flood statistics (flooded area, etc)
'''

#import collections
#import cStringIO
import functools
#import math
#import Queue
import sys
#import time
#import threading
#import urllib2


import ee

## check if the Python imaging libraries used by the mapclient module are installed
#try:
#    from PIL import ImageQt                      # pylint: disable=g-import-not-at-top
#    from PIL import Image, ImageChops                            # pylint: disable=g-import-not-at-top
#except ImportError:
#    print """
#        ERROR: A Python library (PIL) used by the Earth Engine API mapclient module
#        was not found. Information on PIL can be found at:
#        http://pypi.python.org/pypi/PIL
#        """
#    raise

try:
    import PyQt4                         # pylint: disable=g-import-not-at-top
    from PyQt4 import QtCore, QtGui
except ImportError:
    print """
        ERROR: A Python library (PyQt4) used by the Earth Engine API mapclient
        module was not found.
        """
    raise


#import mapclient_qt # Load the core GUI tools

from mapclient_qt import MapViewWidget

import modis.flood_algorithms


# Calendar widget to select a date
class DatePickerWidget(QtGui.QWidget):
    '''Simple calendar widget to select a date'''
    def __init__(self, callback):
        super(DatePickerWidget, self).__init__()
        
        self.datePicker = QtGui.QCalendarWidget(self)
        self.datePicker.clicked.connect(callback)

        # Set up all the components in a box layout
        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.datePicker)

        self.setLayout(hbox) # Call QT function derived from parent QWidget class



# TODO: Add a message box in additon to using the console!


class FloodDetectParams:
    '''Stores the parameters used by the flood detection algorithm'''    
    def __init__(self):
        '''Construct with default parameters'''
        self.changeDetectThreshold = -3.0
        self.waterMaskThreshold    =  3.0
        self.statisticsRegion      = None # TODO: How to set this?
    
    def toString(self):
        print 'Change threshold  = ' + str(self.changeDetectThreshold)
        print 'Mask threshold    = ' + str(self.waterMaskThreshold)
        print 'Statistics region = ' + str(self.statisticsRegion.getInfo()['coordinates'])


class ProductionGui(QtGui.QMainWindow):
    '''This sets up the main viewing window in QT, fills it up with aMapView,
       and then forwards all function calls to it.'''
    
    def __init__(self, parent=None):
        # First set up the flood detection stuff
        self.detectParams = FloodDetectParams()
        self.floodDate      = None # Date of the flood to analyze.
        self.lowResModis    = None # 250m Modis image on the date.
        self.highResModis   = None # 500m Modis image on the date.
        self.compositeModis = None # MODIS display image consisting of bands 1, 2, 6
        self.landsatPrior   = None # First landsat image < date.
        self.landsatPost    = None # First landsat image >= the date.
        self.demImage       = None # DEM image
        self.eeFunction     = None # Flood detection results
        
        # Now set up all the GUI stuff!
        QtGui.QWidget.__init__(self, parent)
        self.mapWidget = MapViewWidget()
        
        # Set up all the components in a vertical layout
        vbox = QtGui.QVBoxLayout()
        
        # Add a horizontal row of widgets at the top
        topHorizontalBox = QtGui.QHBoxLayout()
        
        # Add a date selector to the top row of widgets
        DEFAULT_START_DATE = ee.Date.fromYMD(2006, 7, 18)
        self.floodDate = DEFAULT_START_DATE
        dateString     = '2006/7/18' # TODO: Generate from the default start date
        self.dateButton = QtGui.QPushButton(dateString, self)
        self.dateButton.setMinimumSize(200, 20) # TODO: Move these constants
        self.dateButton.setMaximumSize(200, 20)
        self.dateButton.clicked[bool].connect(self.__showCalendar)
        topHorizontalBox.addWidget(self.dateButton)
        
        # Add a "Set Region" button to the top row of widgets
        self.regionButton = QtGui.QPushButton('Set Processing Region', self)
        self.regionButton.setMinimumSize(200, 20) # TODO: Move these constants
        self.regionButton.setMaximumSize(200, 20)
        self.regionButton.clicked[bool].connect(self.__setRegionToView)
        topHorizontalBox.addWidget(self.regionButton)

        # Add a "Load Images" button to the top row of widgets
        self.loadImagesButton = QtGui.QPushButton('Load Images', self)
        self.loadImagesButton.setMinimumSize(100, 20) # TODO: Move these constants
        self.loadImagesButton.setMaximumSize(100, 20)
        self.loadImagesButton.clicked[bool].connect(self.__loadImageData)
        topHorizontalBox.addWidget(self.loadImagesButton)

        # Add a "Detect Flood" button to the top row of widgets
        self.loadFloodButton = QtGui.QPushButton('Detect Flood', self)
        self.loadFloodButton.setMinimumSize(100, 20) # TODO: Move these constants
        self.loadFloodButton.setMaximumSize(100, 20)
        self.loadFloodButton.clicked[bool].connect(self.__loadFloodDetect)
        topHorizontalBox.addWidget(self.loadFloodButton)

        # Add the row of widgets on the top of the GUI
        vbox.addLayout(topHorizontalBox)
        # Add the main map widget
        vbox.addWidget(self.mapWidget)
        
        
        # First set up some sliders to adjust thresholds
        # - Currently we have two thresholds
        sliderParams = ['Change Detection Threshold', 'Water Mask Threshold']
        paramMin     = [-10, -10]
        paramMax     = [ 10,  10]
        defaultVal   = [-3, 3]
        
        NAME_WIDTH    = 250
        SLIDER_HEIGHT = 20
        SLIDER_WIDTH  = 400
        NUM_TICKS     = 4
        
        # Build each slider one at a time
        self.sliderList = []
        for name, minVal, maxVal, default in zip(sliderParams, paramMin, paramMax, defaultVal):
            
            # Set up this value slider
            slider = QtGui.QSlider(QtCore.Qt.Horizontal, self)
            slider.setRange(minVal, maxVal) 
            slider.setValue(default)
            valRange = maxVal - minVal
            slider.setTickInterval(valRange/NUM_TICKS) # Add five tick marks
            slider.setMinimumSize(SLIDER_WIDTH, SLIDER_HEIGHT)
            slider.setMaximumSize(SLIDER_WIDTH, SLIDER_HEIGHT)
            # Use 'partial' to send the param name to the callback function
            callbackFunction = functools.partial(self.__handleParamChange, parameterName=name) 
            slider.valueChanged.connect(callbackFunction) # Whenever the slider is moved, trigger callback function
            self.sliderList.append(slider) # TODO: Do we need this?
        
            # Make box with the name
            nameBox = QtGui.QLabel(name, self)
            nameBox.setMinimumSize(NAME_WIDTH, SLIDER_HEIGHT)
            nameBox.setMaximumSize(NAME_WIDTH, SLIDER_HEIGHT)
            
            # Put the name to the left of the slider
            hbox = QtGui.QHBoxLayout()
            hbox.addWidget(nameBox)
            hbox.addWidget(slider)
            
            # Stick the horizontal box on the bottom of the main vertical box
            vbox.addLayout(hbox)

        # QMainWindow requires that its layout be set in this manner
        mainWidget = QtGui.QWidget()
        mainWidget.setLayout(vbox)
        self.setCentralWidget(mainWidget)
        
        # This is the initial window size, but the user can resize it.
        self.setGeometry(100, 100, 720, 720) 
        self.setWindowTitle('EE Flood Detector Tool')
        self.show()


    def __unloadCurrentImages(self):
        '''Just unload all the current images. Low level function'''
        if self.compositeModis:
            self.mapWidget.removeFromMap(self.compositeModis)
        if self.landsatPrior:
            self.mapWidget.removeFromMap(self.landsatPrior)
        if self.landsatPost:
            self.mapWidget.removeFromMap(self.landsatPost)
        if self.demImage:
            self.mapWidget.removeFromMap(self.demImage)

    def __displayCurrentImages(self):
        '''Add all the current images to the map. Low level function'''
        # TODO: Come up with a method for setting the intensity bounds!
        LANDSAT_GAIN = [1.5, 1.6, 1.0]
        MODIS_RANGE  = [0, 3000]
        DEM_RANGE    = [0, 1000]
        if self.landsatPrior:
            self.mapWidget.addToMap(self.landsatPrior, {'bands': ['30', '20', '10'], 'gain': LANDSAT_GAIN
                                                        }, 'LANDSAT Pre-Flood',     False)
        else:
            print 'Failed to find prior LANDSAT image!'
        if self.landsatPost:
            self.mapWidget.addToMap(self.landsatPost, {'bands': ['30', '20', '10'], 'gain': LANDSAT_GAIN
                                                       }, 'LANDSAT Post-Flood',    True)
        else:
            print 'Failed to find post LANDSAT image!'
        if self.compositeModis:
            self.mapWidget.addToMap(self.compositeModis, {'bands': ['sur_refl_b01', 'sur_refl_b02', 'sur_refl_b06'],
                                                          'min': MODIS_RANGE[0], 'max': MODIS_RANGE[1]}, 'MODIS Channels 1/2/6',  False)
        else:
            print 'Failed to find MODIS image!'
        if self.demImage:
            self.mapWidget.addToMap(self.demImage, {'min': DEM_RANGE[0], 'max': DEM_RANGE[1]}, 'Digital Elevation Map', False)
        else:
            print 'Failed to find DEM!'

    def __selectLandsatBands(self, eeLandsatFunc):
        '''Given a raw landsat image, pick which bands to view'''
        if not eeLandsatFunc:
            return None
        
        # Select the bands to view
        # - These numbers are for landsat 5
        bandNamesIn  = ['10', '20', '30', '40', '50', '60', '70']
        bandNamesOut = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7']
        
        if eeLandsatFunc.getInfo()['bands']:
            pass # TODO: Need to search the band info better!
            #if '80' in eeLandsatFunc.getInfo()['bands']: # Landsat 7 has more bands
            #    bandNamesIn.append('80')
            #    bandNamesOut.append('B8')
            #eeLandsatFunc = self.landsatPrior.select(bandNamesIn, bandNamesOut) # Select and rename the bands
        else: # The image is invalid!
            eeLandsatFunc = None
        return eeLandsatFunc


    def __pickLandsatImage(self, eeImageCollection, bounds, chooseLast=False):
        '''Picks the best image from an ImageCollection of Landsat images'''
        
        
        # We require the LANDSAT image to contain the center of the analysis region,
        #  otherwise we tend to get images with minimal overlap.
        geoLimited = eeImageCollection.filterBounds(bounds.centroid())
        
        # TODO: How to sort by this property?
        for f in geoLimited.getInfo()['features']:
            print '==================\n\n'
            print f['properties']['ACQUISITION_DATE']
        
        # Now select the first or last image
        return geoLimited.limit(1).mean()

    def __loadImageData(self):
        '''Updates the MODIS and LANDSAT images for the current date'''
        
        print '---Calling loadImageData'
        
        # Check that we have all the information we need
        bounds = self.detectParams.statisticsRegion
        if (not self.floodDate) or (not bounds):
            print "Can't load any images until the date and bounds are set!"
            return
 
        # Unload all the current images
        self.__unloadCurrentImages()

        # Set up the search range of dates for each image type
        MODIS_SEARCH_RANGE_DAYS   = 1  # MODIS updates frequently so we can have a narrow range
        LANDSAT_SEARCH_RANGE_DAYS = 30 # LANDSAT does not update often so we need a large search range
        modisStartDate        = self.floodDate # Modis date range starts from the date
        modisEndDate          = self.floodDate.advance(   MODIS_SEARCH_RANGE_DAYS,   'day')
        landsatPriorStartDate = self.floodDate.advance(-1*LANDSAT_SEARCH_RANGE_DAYS, 'day') # Prior landsat stops before the date
        landsatPriorEndDate   = self.floodDate.advance(-1,                           'day')
        landsatPostStartDate  = self.floodDate # Post landsat starts at the date
        landsatPostEndDate    = self.floodDate.advance(   LANDSAT_SEARCH_RANGE_DAYS, 'day')
        
        # Load the two LANDSAT images
        LANDSAT_TYPE = 'L5_L1T' # TODO: Allow use of landsat 7!
        priorLandsatCollection = ee.ImageCollection(LANDSAT_TYPE).filterDate(landsatPriorStartDate, landsatPriorEndDate)
        postLandsatCollection  = ee.ImageCollection(LANDSAT_TYPE).filterDate(landsatPostStartDate,  landsatPostEndDate)

        self.landsatPrior = self.__pickLandsatImage(priorLandsatCollection, bounds, chooseLast=True)
        self.landsatPost  = self.__pickLandsatImage(postLandsatCollection,  bounds)
        
        # Select the bands to view
        self.landsatPrior = self.__selectLandsatBands(self.landsatPrior)
        self.landsatPost  = self.__selectLandsatBands(self.landsatPost)
        
        # Load the two MODIS images and create a composite
        self.highResModis   = ee.ImageCollection('MOD09GQ').filterBounds(bounds).filterDate(modisStartDate, modisEndDate).limit(1).mean();
        self.lowResModis    = ee.ImageCollection('MOD09GA').filterBounds(bounds).filterDate(modisStartDate, modisEndDate).limit(1).mean();
        self.compositeModis = self.highResModis.addBands(self.lowResModis.select('sur_refl_b06'))

        # Load a DEM
        demName = 'CGIAR/SRTM90_V4' # The default 30m global DEM
        #if (): # TODO: Determine if the bounds are located in the US!
        #    demName = 'ned_13' # The US 10m DEM
        self.demImage = ee.Image(demName)
        
        # Now add all the images to the map!
        self.__displayCurrentImages()


    def __loadFloodDetect(self):
        '''Creates the Earth Engine flood detection function and adds it to the map'''
        
        print '---Calling loadFloodDetect'
        
        # Check prerequisites
        if (not self.highResModis) or (not self.floodDate) or (not self.detectParams.statisticsRegion):
            print "Can't detect floods without image data and flood date!"
            return
        
        # Remove the last EE function from the map
        if self.eeFunction:
            self.mapWidget.removeFromMap(self.eeFunction)
        
        # Generate a new EE function
        #print self.detectParams.toString()
        self.eeFunction = modis.flood_algorithms.history_diff_core(self.highResModis,
                                        self.floodDate, self.detectParams.waterMaskThreshold,
                                        self.detectParams.changeDetectThreshold, self.detectParams.statisticsRegion)
        self.eeFunction = self.eeFunction.mask(self.eeFunction)
        
        # Add the new EE function to the map
        # TODO: Set display parameters with widgets
        OPACITY = 0.5
        COLOR   = '00FFFF'
        self.mapWidget.addToMap(self.eeFunction, {'min': 0, 'max': 1, 'opacity': OPACITY, 'palette': COLOR}, 'Flood Detection Results', True)

    def __handleParamChange(self, value, parameterName='DEBUG'):
        '''Reload an EE algorithm when one of its parameters is set in the GUI'''
        if parameterName == 'Change Detection Threshold':
            self.detectParams.changeDetectThreshold = value
            return
        if parameterName == 'Water Mask Threshold':
            self.detectParams.waterMaskThreshold = value
            return
        print 'WARNING: Parameter ' + parameterName + ' is set to: ' + str(value)
        
    def __setDate(self, date):
        '''Sets the current date'''
        self.floodDate = ee.Date.fromYMD(date.year(), date.month(), date.day()) # Load into an EE object
        self.dateButton.setText(date.toString('yyyy/MM/dd')) # Format for humans to read
        
    def __setRegionToView(self):
        '''Sets the processing region to the current viewable area'''
        # Extract the current viewing bounds as [minLon, minLat, maxLon, maxLat]
        lonLatBounds = self.mapWidget.GetMapBoundingBox() # TODO: This function does not work!!!!
        print 'Setting region to: ' + str(lonLatBounds)
        self.detectParams.statisticsRegion = apply(ee.geometry.Geometry.Rectangle, lonLatBounds)

    def __showCalendar(self):
        '''Pop up a little calendar window so the user can select a date'''
        menu   = QtGui.QMenu(self)
        action = QtGui.QWidgetAction(menu)
        item   = DatePickerWidget(self.__setDate) # Pass in callback function
        action.setDefaultWidget(item)
        menu.addAction(action)
        menu.popup(QtGui.QCursor.pos())
        

    def keyPressEvent(self, event):
        """Handle keypress events."""
        if event.key() == QtCore.Qt.Key_Q:
            QtGui.QApplication.quit()

    def __getattr__(self, attr):
        '''Forward any undefined function call to the main map widget'''
        try:
            return getattr(self.mapWidget, attr) # Forward the call to the MapViewWidget class
        except:
            print str(attr)
            raise AttributeError(attr) # This happens if the MapViewWidget class does not support the call



































