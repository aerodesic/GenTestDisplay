#-----------------------------------------------------------------------------
# Name:        Graph.py
# Purpose:     Display a graph of a set of points
#
# Author:      Gary Oliver <go@ao-cs.com>
#
# Created:     2011/06/14
# RCS-ID:      $Id: LedPanel.py $
# Licence:     <your licence>
#-----------------------------------------------------------------------------

# from numpy.fft import fft
from scipy.fftpack import fft

import math
import os
import wx
from threading import RLock as Lock
import traceback


def step_range(start, end, step):
    while start <= end:
        yield start
        start += step

class PlotGraph(wx.Panel):
    __DEFAULT_NUM_POINTS = 64
    __DEFAULT_YMIN = None
    __DEFAULT_YMAX = None
    __DEFAULT_GAIN = 1.0
    __DEFAULT_CLAMP = False
    __DEFAULT_BARCHART = False
    __DEFAULT_IMAGINARY = False
    __DEFAULT_TYPE = None
    __DEFAULT_X_GRID = 5
    __DEFAULT_Y_GRID = 5
    __DEFAULT_PLOTTYPE = "ts"
    __DEFAULT_XLABELFUN = lambda self,v:"%d"%v
    __DEFAULT_YLABELFUN = lambda self,v:"%d"%v
    __DEFAULT_YCONVERT = lambda self,y:y
    __DEFAULT_XMIN = None
    __DEFAULT_XMAX = None
    __DEFAULT_SUBGRID = 0
    __DEFAULT_RESULTS = []
    __DEFAULT_ZERO = 0

    def __init__(self, parent, id=-1, pos=wx.DefaultPosition, size=wx.DefaultSize,
                 style=wx.RAISED_BORDER | wx.FULL_REPAINT_ON_RESIZE,
                 name=u"Graph"):
        wx.Panel.__init__(self, parent, id, pos, size, style, name)
        
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Bind(wx.EVT_SIZE, self.OnSize)
        
        self.in_points = {}
        self.in_numpoints = self.__DEFAULT_NUM_POINTS
        self.out_points = {}
        self.channel_colors = {}
        self.params = {}
        self.xmin = self.__DEFAULT_XMIN
        self.xmax = self.__DEFAULT_XMAX
        self.ymin = self.__DEFAULT_YMIN
        self.ymax = self.__DEFAULT_YMAX
        self.barchart = self.__DEFAULT_BARCHART
        self.clamp = self.__DEFAULT_CLAMP
        self.gain = self.__DEFAULT_GAIN
        self.xlabelfun = self.__DEFAULT_XLABELFUN
        self.ylabelfun = self.__DEFAULT_YLABELFUN
        self.subgrid = self.__DEFAULT_SUBGRID
        self.results = self.__DEFAULT_RESULTS
        self.next_default_color = 0
        self.lock = Lock()
 
    def Stop(self):
	    pass

    def OnPaint(self, event): 
        dc = wx.PaintDC(self)
        # dc.SetBackground(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW))
        dc.SetBackground(wx.TheBrushList.FindOrCreateBrush(self.GetBackgroundColour(), wx.SOLID))
        dc.Clear()
        self.DrawGraph(dc)
        event.Skip()

    # Hook for drawing panel with a specific DC        
    def PaintWithDC(self, dc):
        self.DrawGraph(dc)
        
    def DrawGraph(self, dc):
        w = self.GetSize().GetWidth()
        h = self.GetSize().GetHeight()
        # print("PlotGraph: DrawGraph (%d, %d)" % (w, h))

        x0 = w * 0.1
        y0 = h * 0.1
        w  = w - 2*x0
        h  = h - 2*y0
        
        # Draw Rect coords
        dc.SetPen(wx.Pen(wx.BLACK))
        dc.SetBrush(wx.Brush(wx.BLACK, wx.TRANSPARENT))
        dc.DrawRectangle(x0, y0, w, h)
        
        for y in range(1, self.ygrid):
            offset = int(round(y * h / self.ygrid))
            dc.DrawLine(x0, y0 + offset, x0 + w, y0 + offset)

        for x in range(1, self.xgrid):
            offset = int(round(x * w / self.xgrid))
            dc.DrawLine(x0 + offset, y0, x0 + offset, y0 + h)

        if self.xmin is not None and self.xmax is not None:
            for x in range(0, self.xgrid + 1):
                xlabel = self.xlabelfun(self.xmin + round((self.xmax - self.xmin) * x / self.xgrid))
                (text_width, text_height) = dc.GetTextExtent(xlabel)
                dc.DrawText(xlabel,
                        x0 + x * w / self.xgrid - text_width / 2,
                        y0 + h)
         
        if self.subgrid != 0:
            # Put in subgrid on x and y
            yrange = self.ymax - self.ymin
            xrange = self.xmax - self.xmin

            for y in step_range(0, yrange, round(yrange / self.ygrid) / self.subgrid):
                offsety = (y * h) / yrange

                for x in step_range(0, xrange, round(xrange / self.xgrid) / self.subgrid):
                     offsetx = (x * w) / xrange
                     dc.DrawPoint(x0 + offsetx, y0 + offsety)
                     # print("subgrid at (%d,%d) = (%d,%d)" % (x, y, offsetx, offsety))
                     
        if self.barchart:
            dc.SetBrush(wx.Brush(wx.RED, wx.SOLID))

        # For all channels and points in channel, compute the min/max y
        # Display will receive the values of by by X coord,
        display = {}
        points = 0
        for channel in self.out_points:
            # print("channel %s len %d" % (channel, len(self.out_points[channel])))
            if len(self.out_points[channel]) > 5:
                display[channel] = []

                # Go through all lists and produce the values of points in user units.
                # Keep track of max and min before we actually plot the data

                for p in range(0, self.zero):
                    display[channel].append((p, 0))

                for p in range(self.zero, len(self.out_points[channel])):
                    if self.plottype in [ "cfft", "fft" ]:
                        yval = math.sqrt(self.out_points[channel][p].real*self.out_points[channel][p].real + self.out_points[channel][p].imag*self.out_points[channel][p].imag)
                    else:
                        yval = self.out_points[channel][p].real

                    # Apply gain after
                    yval *= self.gain

                    if self.clamp:
                        # yval = ymax
                        if yval < self.ymin:
                            yval = self.ymin
                        if yval > self.ymax:
                            yval = self.ymax

                    display[channel].append((p, self.yconvert(yval)))
                    points += 1

        # print("display %s" % display)
        # print("points %s" % [ point for channel in display for point in display[channel] ])

        # Compute min/max over entire array of channels
        if points != 0 and self.ymin is None and self.ymax is None:
            ymin = min(y for x,y in (point for channel in display for point in display[channel]))
            ymax = max(y for x,y in (point for channel in display for point in display[channel]))

            if ymin == ymax:
                ymax = ymax + 1
    
            # print("points %d min %.3f max %.3f" % (points, ymin, ymax))
        else:
            ymin = self.ymin
            ymax = self.ymax

        if ymax is not None:
            # Plot and label the Y axis
            for y in range(0, self.ygrid + 1):
                ylabel = self.ylabelfun(ymax - (ymax - ymin) * y / self.ygrid)
                (text_width, text_height) = dc.GetTextExtent(ylabel)
                dc.DrawText(ylabel,
                        x0 - text_width - 10,
                        y0 + y * h / self.ygrid - text_height / 2)
    
            # Now plot the channels
            for channel in display:
                # Choose a color
                if channel in self.channel_colors:
                    dc.SetPen(wx.Pen(self.channel_colors[channel]))
                else:
                    dc.SetPen(wx.Pen(wx.RED))
    
                lastx = None
                lasty = None
    
                # Now plot the results
                for p, y in display[channel]:
                    x = int(round(p * w / (len(self.out_points[channel]) - 1) + 0.5))
                    y = int(round((y - ymin) * h / (ymax - ymin) + 0.5))
    
                    if lastx != None:
                        if self.barchart:
                            dc.DrawRectangle(x0 + lastx, y0 + h - lasty, x - lastx, lasty)
                        else:
                            dc.DrawLine(x0 + lastx, y0 + h - lasty, x0 + x, y0 + h - y)
    
                    lastx = x
                    lasty = y 

    def OnSize(self, event):
        # print("PlotGraph: OnSize %s", event.GetSize())
        self.Refresh()
        event.Skip()
    
    # Return the sum of the values in the saved points list from start to end.
    def GetValue(self, start, end, channel="default"):
        with self.lock:
            if channel in self.out_points and start >= 0 and end < len(self.out_points[channel]) and start <= end and len(self.out_points[channel]) != 0:
                sum = sum(self.out_points[channel][element] for element in range(start, end+1))
            else:
                sum = 0

            # print("GetValue from %d to %d returning %s" % (start, end, str(sum)))

        return sum

 
    # Accept a point or a list of points
    def __AddValue(self, value, channel):
        if type(value) == tuple or type(value) is list:
            for item in value:
                self.__AddValue(item, channel)

        else:
            if type(value) == complex:
                x = value.real
                y = value.imag
         
            else:
                x = value
                y = 0
            
            if self.plottype == "phase":
                # Compute phase of values
                in_value = complex(math.atan2(y, x), 0)

            elif self.plottype == "cfft":
                # make X Y into Rho Theta
                in_value = complex(math.sqrt(x*x + y*y), math.atan2(y, x))

            else:
                # Else just amplitude as real
                in_value = complex(x, 0)

            self.in_points[channel].append(in_value)

    def SetChannelColor(self, channel, color):
        with self.lock:
            self.channel_colors[channel] = color

    def DeleteChannel(self, channel):
        with self.lock:
            if channel in self.in_points:
                del self.in_points[channel]
            if channel in self.out_points:
                del self.out_points[channel]

    # Assign a point or points to the graph.  If the input is a list[] it is iterated
    # to assign each individual point table.  For a complex number, the real and imaginary
    # components form X and Y.  Otherwise the points is assumed to be a tuple and X is
    # formed from the first component and Y from the second.
    def SetValue(self, value, channel="default"):
        with self.lock:
            # print("Graph SetValue(%s, '%s') %s" % (self.plottype, channel, str(value)))

            # Prime the point list if nothing set so far
            if channel not in self.in_points:
                # print("SetValue: channel %s resetiting points" % (channel))
                self.in_points[channel] = []
                self.out_points[channel] = []

            # Add the value to the list
            self.__AddValue(value, channel)

            # Trim extra points
            if len(self.in_points[channel]) > self.in_numpoints:
                # print("channel %s trimming %d points; now is %d" % (channel, len(self.in_points[channel]) - self.in_numpoints, len(self.in_points[channel])))
                try:
                    self.in_points[channel] = self.in_points[channel][(len(self.in_points[channel]) - self.in_numpoints):]
                except Exception as e:
                    traceback.print_exc()
                    print("len in_points['%s'] %d" % (channel, len(self.in_points[channel])))
                    print("in_numpoints %d" % (self.in_numpoints))
                    print("type of self.in_numpoints %s" % (type(self.in_numpoints)))
                    

            # Compute the function if one is defined
            if len(self.in_points[channel]) > 2:
                if self.plottype in [ "cfft", "fft" ]:
                    # Perform fft of point vector and produce result (one half)
                    self.out_points[channel] = fft(self.in_points[channel]).tolist()
                    # print("channel %s in_points %d  out_points %d" % (channel, len(self.in_points[channel]), len(self.out_points[channel])))
                    self.out_points[channel] = self.out_points[channel][:int(len(self.out_points[channel])/2)+1]
                else:
                    self.out_points[channel] = self.in_points[channel]
            else:
                self.out_points[channel] = []
    
            results = {}

            # See if a published value to return
            if "fft" in self.results:
                results["fft"] = self.out_points[channel];

            if "average" in self.results:
                results["average"] = sum(self.out_points[channel]) / len(self.out_points[channel])

            if "thd" in self.results and self.plottype in [ "cfft", "fft" ]:
                results["thd"] = self.CalcTHD(channel)

            self.Refresh()

            # print("Graph SetValue returning %s" % results)

        return results if len(results) != 0 else None
        
    def CalcTHD(self, channel="default"):
        if len(self.out_points[channel]) < 5:
            results = 0

        else:
            # Omit the DC channel
            max_data_element = max(element.real for element in self.out_points[channel][1:])

            sq_sum = sum(element.real**2 for element in self.out_points[channel][1:])

            sq_harmonics = sq_sum - max_data_element ** 2

            results = math.sqrt(100 * sq_harmonics) / max_data_element

        return results


    def SetRange(self, yrange):
        with self.lock:
            self.yrange = yrange

    def EvalParam(self, param, defvalue = False):
        with self.lock:
            if not param in self.params:
                self.params[param] = defvalue

            return self.params[param]

    # Params are a dictionary.  Save and evaluate for missing items
    def SetParams(self, params):
        with self.lock:
            self.params = params

            self.in_numpoints  = int(self.EvalParam("points",        self.__DEFAULT_NUM_POINTS))
            self.ymin          = self.EvalParam("ymin",          self.__DEFAULT_YMIN)
            self.ymax          = self.EvalParam("ymax",          self.__DEFAULT_YMAX)
            self.clamp         = self.EvalParam("clamp",         self.__DEFAULT_CLAMP)
            self.plottype      = self.EvalParam("plottype",      self.__DEFAULT_PLOTTYPE)
            self.gain          = self.EvalParam("gain",          self.__DEFAULT_GAIN)
            self.barchart      = self.EvalParam("bar",           self.__DEFAULT_BARCHART)
            self.xlabelfun     = self.EvalParam("xlabelfun",     self.__DEFAULT_XLABELFUN)
            self.ylabelfun     = self.EvalParam("ylabelfun",     self.__DEFAULT_YLABELFUN)
            self.yconvert      = self.EvalParam("yconvert",      self.__DEFAULT_YCONVERT)
            self.xmin          = self.EvalParam("xmin",          self.__DEFAULT_XMIN)
            self.xmax          = self.EvalParam("xmax",          self.__DEFAULT_XMAX)
            self.xgrid         = self.EvalParam("xgrid",         self.__DEFAULT_X_GRID)
            self.ygrid         = self.EvalParam("ygrid",         self.__DEFAULT_Y_GRID)
            self.subgrid       = self.EvalParam("subgrid",       self.__DEFAULT_SUBGRID)
            self.results       = self.EvalParam("results",       self.__DEFAULT_RESULTS)

            if self.results is not list and self.results is not tuple:
                self.results = ( self.results )
                
            self.zero          = int(self.EvalParam("zero",          self.__DEFAULT_ZERO))

            print("params is %s"            % str(self.params))
            print("in_numpoints set to %d"  % self.in_numpoints)
            print("plottype is %s"          % self.plottype)
            print("gain is %s"              % self.gain)
            print("clamp is %s"             % self.clamp)
            print("ymin is %s"              % self.ymin)
            print("ymax is %s"              % self.ymax)
            print("bar is %s"               % self.barchart)
            print("xmin is %s"              % str(self.xmin))
            print("xmax is %s"              % str(self.xmax))
            print("xgrid is %d"             % self.xgrid)
            print("ygrid is %d"             % self.ygrid)
            print("subgrid is %f"           % self.subgrid)
            print("results is %s"           % str(self.results))
            print("zero is %d"              % self.zero)

    def Reset(self):
        print("Graph: Reset called")
        pass

