#!/usr/bin/env python

#
# Some functions to handle ARGUS IFU data
#

import numarray as N
import pylab as P
from PyCigale import read_fits,write_fits,shift
import scipy.stats as S
from mpfit import mpfit
import time
#from pyIDL import idl as IDL
import pickle
import scipy.signal.signaltools as Sig
from scipy.fftpack import fft
from time import sleep

#from pyraf import iraf
#iraf.module.rv()
#fxcor=iraf.module.rv.fxcor

import pyfits

#####################################
#### GLOBAL VARIABLES AND CONSTANTS
#####################################
c=2.99792E5
#                 Pa19         18  ....
Paschen=N.array([8413.317, 8437.955, 8467.253, 8502.483, 8545.382, 8598.392, 8665.018, 8750.473, 8862.783, 9014.910, 9229.014])

#PschenStrengths     9/10  10/10  11/10  12/10    ...                                            19/10
PaschStren=N.array([1.3812, 1.0, 0.7830, 0.6131, 0.4801, 0.3759, 0.2943, 0.2477, 0.2084, 0.1754, 0.1476])

# wrong temperature
#PaschStren=N.array([1.0, 0.7853, 0.6167, 0.4843, 0.3803, 0.2987, 0.2542, 0.2164, 0.1842, 0.1567])

#PaschStren /= PaschStren[0]
PaschStren=PaschStren[::-1]

EmissionLines=N.array([9068.6,8446,8579,8617])
CaT=N.array([8498., 8542., 8662.])
Sulfur=9068.6

#Lamb0=8182.43
#SpecLen=1407
#Step=0.85

Lamb0=8183.43
SpecLen=1357
Step=0.85

Lamb0=8183.213
SpecLen=2715
Step=0.425

#Lamb0=8182.
#Step=0.19996649916247891
#SpecLen=5980

#SpecLenOrg=5980
SpecLenOrg=2715

dimX=22
dimY=14

#skyregion=N.array([8750,8800])
skyregion=N.array([8810,8876])

#skyregion=N.array([8860,8910])

########################
## CONSTRUCTING THE CUBE
########################

def spec2cube(filename,tablefile='/home/tom/projekte/PyGalKin/argus-fibres.txt'):
    pass
    

def image2cube(data,tablefile='/home/tom/projekte/PyGalKin/argus-fibres.txt'):
    """allows both a filename and a 2d-array as input. the latter has to be flipped already """

    if type(data) == type(''):
        data=read_fits(data)
        data=data[:,::-1]
    elif type(data) == type(N.array([])):
        pass
    else:
        print 'unknown type of input'
        return -1

    if data.shape[1]==311:
        havesimcal=False
        missing=4
    elif data.shape[1]==316:
        havesimcal=True
        missing=4
    elif data.shape[0]==317:
        havesimcal=True
        missing=3
        data=N.transpose(data)
    else:
        print 'unknown type of input'
        return -1

    cube=N.zeros((dimX,dimY,SpecLenOrg),'Float32')
    sky=N.array([],'Float32')
    if havesimcal: simcal=N.array([],'Float32')
    
    file=open(tablefile,'r')

    # two header lines and missing spectra
    file.readline()
    file.readline()
    print str(missing) + ' missing spectra'
    for i in N.arange(missing): file.readline()

    
    for line in file.readlines():
        line=line.split()
        index=int(line[1])-(missing+1)
        
        if 'Sky' in line[4]:
            sky=N.concatenate((sky,data[:,index]))
           
        elif 'Calibration' in line[4]:
            if havesimcal: simcal=N.concatenate((simcal,data[:,index]))
            else: missing+=1
        else:
            x,y=int(line[-3])-1,int(line[-2])-1
            #print x,y,index
            cube[x,y,:]=data[:,index]
        

    file.close()
    sky.setshape(sky.nelements()/SpecLenOrg,SpecLenOrg)
    #badpixels(cube)
    if havesimcal:
        simcal.setshape(simcal.nelements()/SpecLenOrg,SpecLenOrg)
        return cube,sky,simcal
    else: return cube,sky

def badpixels(data, value=0):
    """ sets the known bad spectra in a cube to value"""

    if len(data.shape)==3:
        data[0,0,:]=value
        data[1,0,:]=value
        data[20,0,:]=value
        data[21,0,:]=value
        data[0,13,:]=value
        data[1,13,:]=value
        data[20,13,:]=value
        data[21,13,:]=value
        data[3,4,:]=value
        data[20,8,:]=value
        data[20,9,:]=value
        data[20,10,:]=value
    elif len(data.shape)==2:
        data[0,0]=value
        data[1,0]=value
        data[20,0]=value
        data[21,0]=value
        data[0,13]=value
        data[1,13]=value
        data[20,13]=value
        data[21,13]=value
        data[3,4]=value
        data[20,8]=value
        data[20,9]=value
        data[20,10]=value


#####################
## SUBRTACTING STUFF
#####################
def skysub(data,sky,factor=1.9,region=skyregion):
    """ wants data in 2d or 3d, sky is first medianned to 1d, then grown"""
    shape=data.getshape()
    if len(data.shape) == 3:
        data.shape=(shape[0]*shape[1],shape[2])
    sky=medianspec(sky)
    #sky=N.resize(sky,data.shape)
    factor=skyfit(data,sky,region)
    dataSS=data.copy()
    for i in N.arange(data.shape[0]):
        dataSS[i]=data[i]-(factor[i]*sky)
    data.shape=shape
    dataSS.shape=shape
    return dataSS

def contSubtr(data,order=6,sigmaclip=1.0,plot=False):
    if len(data.shape)==1: return contFit(data,order=order,sigmaclip=sigmaclip,plot=plot)
    origshape=data.getshape()
    if len(data.shape) == 3:
        data.shape=(origshape[0]*origshape[1],origshape[2])

    contSub=N.zeros(data.shape,'Float32')
    for i in N.arange(data.shape[0]):
        contSub[i,:]=contFit(data[i,:],order=order,sigmaclip=sigmaclip,plot=plot)
        #print str(i)+' done'

    data.shape=origshape
    contSub.shape=origshape
    return contSub
    
def contFit(data,order=6,sigmaclip=1.0,plot=False):

    x=N.arange(len(data))
    poly=P.polyfit(x,data,order)
    #print poly
    subtr=data-P.polyval(poly,x)
    flagged=N.where(N.abs(subtr) > (sigmaclip*S.std(subtr)),x=0,y=subtr)
    corrpoly=P.polyfit(x,flagged,order)
    finalfit=P.polyval(poly,x)+P.polyval(corrpoly,x)
    if plot:
        P.plot(data)
        P.plot(flagged)
        P.plot(finalfit)
        P.plot(data-finalfit)
    return data-finalfit


    

##################################
### PASCHEN AND OTHER LINE FITTING
##################################

def fitAllPaschen(data,err,velRange=None,guessV=None,PaNumbers=[9,10,11,12,14,17],parinfo=None,plot=False,prin=False,quiet=True):
    relevant=N.array([],type='Float32')
    relerr=N.array([],type='Float32')
    once=False
    for p in PaNumbers:
        p=PaLamb(p)
        Left,Right= vel2lamb(guessV-(velRange/2.),p),vel2lamb(guessV+(velRange/2.),p)
        Left,Right=int(lamb2pix(Left)),int(lamb2pix(Right))
        if not once:
            pixels=Right-Left-1
            once=True
        #print Left,Right, pixels
        rel=data[Left:Left+pixels]
        rele=err[Left:Left+pixels]
        
        #rel-=min(rel)
        relevant=N.concatenate((relevant,rel))
        relerr=N.concatenate((relerr,rele))

    
    nlines=len(PaNumbers)
    if parinfo==None:
        parinfo=[]
        parinfo.append({'value':min(relevant), 'fixed':0, 'limited':[0,0],'limits':[min(relevant), max(relevant)], 'step':0.0})
        parinfo.append({'value':pixels*0.5, 'fixed':0, 'limited':[0,0],'limits':[0.0, float(pixels)], 'step':0.0})
        parinfo.append({'value':pixels*0.05, 'fixed':0, 'limited':[0,0],'limits':[0.0, pixels*0.5], 'step':0.0})
        for i in range(nlines):
            #print max(relevant[i*pixels:(i+1)*pixels])
            parinfo.append({'value':max(relevant[i*pixels:(i+1)*pixels])-min(relevant), 'fixed':0, 'limited':[0,0],'limits':[0.0, max(relevant[i*pixels:(i+1)*pixels])*1.2], 'step':0.0})

    x=N.arange(len(relevant))
    
    fa = {'x':x, 'y':relevant, 'err':relerr, 'n':nlines}
    
    try:
        fit=mpfit(funcAllPaschen,functkw=fa,parinfo=parinfo,maxiter=200,quiet=quiet,gtol=1E-5)
    except OverflowError:
        return -1

    print 'status: ',fit.status
    
    if plot==True:
        P.plot(relevant,'r')
        P.plot(funcAllPaschen(fit.params,x=N.arange(len(relevant)),n=nlines,returnmodel=True),'b')
    if prin==True:
        print fit.niter,fit.params,fit.status
    
    return fit.params


def funcAllPaschen(p, fjac=None, x=None, y=None, err=None, n=None,returnmodel=False):
    model=N.zeros(len(x),'Float32')
    pixels=len(x)/n
    
    for i in N.arange(n):
        #print x[i*pixels:(i+1)*pixels]
        model[i*pixels:(i+1)*pixels]+=p[i+3]*N.exp( -1* ((x[i*pixels:(i+1)*pixels]-(p[1]+(i*pixels)))**2) / (2*(p[2]**2)) )
        #P.plot(model)
        #sleep(0.3)
    model+=p[0]
    
    #P.plot((y-model))
    #P.plot(model)
    #P.plot(y)

    if returnmodel==True:
        return model
    else:
        status = 0
        return([status, (y-model)/err])


def findLine(data,double=True,velRange=None,guessV=None,restlamb=Sulfur,parinfo=None,plot=False,prin=False,quiet=True):
    
    Left= vel2lamb(guessV-(velRange/2.),restlamb)
    Right= vel2lamb(guessV+(velRange/2.),restlamb)
    Left,Right=int(lamb2pix(Left)),int(lamb2pix(Right))
    
    relevant=data[Left:Right]
    if double:
        fit=fit2gauss(relevant,parinfo=parinfo,plot=plot,prin=prin,quiet=quiet)
        if fit==-1:
            print "fit went wrong!"
            return fit
        PeakPos=N.argmax(twogauss(fit.params,x=N.arange(len(relevant)),returnmodel=True))
    else:
        fit=fitgauss(relevant,parinfo=parinfo,plot=plot,prin=prin,quiet=quiet)
        if fit==-1: return fit
        PeakPos=N.argmax(gauss(fit.params,x=N.arange(len(relevant)),returnmodel=True))

    #Z=pix2lamb(PeakPos+Left) / restlamb
    Z=pix2lamb(fit.params[1]+Left) / restlamb
    #print fit.params,Z,Left
    D1=fit.params[1]-PeakPos
    if double: D2=fit.params[4]-PeakPos
    else: D2=PeakPos
    return Z,fit.params,D1,D2
                                

def emissionVF(data,velRange=None,guessV=None,restlamb=Sulfur,double=False,plot=False):
    origshape=data.getshape()
    if len(data.shape) == 3:
        data.shape=(origshape[0]*origshape[1],origshape[2])

    EmVF=N.zeros(data.shape[0],'Float32')
    Cont=N.zeros(data.shape[0],'Float32')
    Ampl=N.zeros(data.shape[0],'Float32')
    Width=N.zeros(data.shape[0],'Float32')
    for i in N.arange(len(EmVF)):
        
        results=findLine(data[i,:],restlamb=restlamb,velRange=velRange,guessV=guessV,double=double,plot=plot)
        if results==-1:
            Z,params,D1,D2=0.0,[0.0,0.0,0.0,0.0],0.0,0.0
        else:
            Z,params,D1,D2=results

        #print Z
        EmVF[i]=Z
        Cont[i]=params[0]
        if len(params)==4:
            Ampl[i]=params[2]
            Width[i]=params[3]
        else:
            Ampl[i]=params[2]+params[5]
        #print i,EmVF[i]
    
    data.shape=origshape
    EmVF=z2vel(EmVF)
    Width=pix2relvel(Width,restlamb)
    EmVF.shape=(origshape[0],origshape[1])
    Ampl.shape=(origshape[0],origshape[1])
    Cont.shape=(origshape[0],origshape[1])
    Width.shape=(origshape[0],origshape[1])
    
    #print data.shape,EmVF.shape
    #P.matshow(EmVF)
    return EmVF,Width,Ampl,Cont



def interpasch(data,error,velRange=None,guessV=None,PaNumb=10,filename='intPa.dat'):
    sub=data.copy()
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            dat=data[i,j,:].copy()
            err=error[i,j,:].copy()
            if isconstant(dat):
                print 'skipping '+str(i)+' '+str(j)
                sub[i,j,:]=data[i,j,:]
                continue
            print 'Cuttent pixel: %s %s' % (i,j)
            inter=interactplot(dat,err,filename=filename,velRange=velRange,guessV=guessV,i=i,j=j,PaNumb=PaNumb)
            P.show()
            sub[i,j,:]=inter.data - inter.shiftscaled()

    return sub
            

class interactplot:
    def __init__(self,data,error,velRange,guessV,i,j,filename='intPa.dat',PaNumb=10):
        self.odata=data
        self.data=contSubtr(self.odata,order=5)
        self.error=error
        self.velRange=velRange
        self.guessV=guessV
        self.i=i
        self.j=j
        #self.double=double
        self.PaNumb=PaNumb
        self.sn=selav(self.odata/self.error)
        self.step=0.1
        self.fact=1.0
        self.shift=0
        self.file=open(filename,'a')
        self.fig=P.figure(1)#,figsize=(14,10))
        canvas = self.fig.canvas
        canvas.mpl_connect('key_press_event', self.key_press_callback)
        canvas.mpl_connect('button_press_event', self.button_press_callback)
        self.canvas = canvas
        self.measurePa()
        self.makesynt()
        

    def makesynt(self):
        #P.figure(2)
        self.osynt=createPaschen(self.odata,double=True,velRange=self.velRange,guessV=self.guessV,PaNumb=self.PaNumb,plotfit=False)
        self.synt=self.osynt.copy()
        #P.figure(1)
        self.plot()
        
    def fromSulf(self):
        self.osynt=createPaschenSul(self.odata,velRange=self.velRange,guessV=self.guessV,plotfit=False)
        self.synt=self.osynt.copy()
        self.plot()
        
    def measurePa(self):
        params=fitAllPaschen(self.odata,self.error,velRange=self.velRange,guessV=self.guessV,plot=False,prin=False)
        print params
        self.paparams=params

    def shiftscaled(self):
        return shift(self.synt,self.shift)*self.fact

    def plot(self):
        self.fig.clf()

        # Around CaT
        ax=P.axes([0.02,0.68,0.70,0.27])
        P.setp(ax,xticks=[], yticks=[])
        plotspec(self.shiftscaled(),style='-r')
        plotspec(self.data,style='-k')
        plotspec(self.data-self.shiftscaled(),region=[8470,8700],style='-r')
        
        P.title('CaT and Pa 13, 14, 15, 16')
        
        # SIII
        ax=P.axes([0.74,0.68,0.23,0.27])
        self.plotaroundline(Sulfur)
        P.setp(ax,xticks=[], yticks=[])
        P.title('S[III]')

        ## Pa 9
        ax=P.axes([0.02,0.35,0.23,0.27])
        self.plotaroundline(PaLamb(9))
        P.setp(ax,xticks=[], yticks=[])
        P.title('Pa 9')
        ## Pa 10
        ax=P.axes([0.26,0.35,0.23,0.27])
        self.plotaroundline(PaLamb(10))
        P.setp(ax,xticks=[], yticks=[])
        P.title('Pa 10')
        ## Pa 11
        ax=P.axes([0.50,0.35,0.23,0.27])
        self.plotaroundline(PaLamb(11))
        P.setp(ax,xticks=[], yticks=[])
        P.title('Pa 11')
        ## Pa 12
        ax=P.axes([0.74,0.35,0.23,0.27])
        self.plotaroundline(PaLamb(12))
        P.setp(ax,xticks=[], yticks=[])
        P.title('Pa 12')
        
        ## Pa 17
        ax=P.axes([0.02,0.02,0.23,0.27])
        self.plotaroundline(PaLamb(17))
        P.setp(ax,xticks=[], yticks=[])
        P.title('Pa 17')
        
        ## PaStren Ratio
        ax=P.axes([0.28,0.02,0.23,0.27])
        lines=N.array([9,10,11,12,14,17])
        ratio=self.paparams[3:] / PaschStren[19-lines]
        P.plot(lines[::-1],ratio/ratio[-3],'bo')
        P.setp(ax,xticks=[9,10,11,12,14,17])
        P.title('Pa Strength Ratio')

        ## values
        ax=P.axes([0.86,0.02,0.10,0.27])
        P.text(0.1,0.9,'S/N: '+str(int(self.sn)),transform = ax.transAxes)
        P.text(0.1,0.8,'X: %s  Y: %s'%(self.i,self.j),transform = ax.transAxes)
        
        P.setp(ax,xticks=[], yticks=[])
        P.title('Some Values')
        
        self.canvas.draw()

    def plotaroundline(self,lamb):
        region=[vel2lamb(-self.velRange /2.,lamb),vel2lamb(self.velRange /2.,lamb)]
        #print lamb,region, self.velRange, self.guessV
        plotspec(self.shiftscaled(),region=region,style='r',linestyle='steps')
        plotspec(self.data,region=region,style='k',linestyle='steps')
        
        
    def accept(self):
        self.file.write('%s %s %s %s %s\n'%(self.i,self.j,self.PaNumb,self.fact,self.shift))
        self.file.close()
        P.close(self.fig)

    def reject(self):
        self.file.write('%s %s %s\n'%(self.i,self.j,'R'))
        self.file.close()
        P.close(self.fig)
    
    def startover(self):
        self.synt=self.osynt.copy()
        self.data=self.data=contSubtr(self.odata,order=5)
        self.fact=1.0
        self.shift=0
        self.plot()

    def chooseline(self):
        get=raw_input('tell me: ')
        if get == 's': self.fromSulf()
        else:
            self.PaNumb=int(get)
            self.makesynt()
        
        
    def key_press_callback(self,event):
        
        if event.key == '+': self.fact += self.step
        elif event.key == '-': self.fact -= self.step 
        elif event.key == 'l': self.shift -= 1
        elif event.key == 'r': self.shift += 1
        elif event.key == 's': self.smooth()
        elif event.key == 'o': self.startover()
        elif event.key == 'a': self.accept()
        elif event.key == 'q': self.reject()
        elif event.key == 'c': self.chooseline()
        else: print "Unknown key pressed, doing nothing"
        self.plot()
        
    def button_press_callback(self,event):
        pass
        

def createPaschen(data,double=True,velRange=None,guessV=None,plot=False,plotfit=False,PaNumb=9):
    fitresults=findLine(data,double=double,velRange=velRange,guessV=guessV,restlamb=PaLamb(PaNumb),plot=plotfit)
    #print fitresults
    if fitresults==-1:
        return N.zeros(SpecLen,'Float32')
    else:
        Z,paschenparam,D1,D2=fitresults
            
    #print fitresults
    Pasch=Paschen * Z

    # don't subtract continuum
    paschenparam[0]=0.0

    x=N.arange(SpecLen)
    SynthSpec=N.zeros(SpecLen,'Float32')

    Stren=PaschStren / PaschStren[19-PaNumb]
    #print Stren
    for i in N.arange(len(Paschen)):
        para=paschenparam.copy()
        para[2]*=Stren[i]
        para[1]=lamb2pix(Paschen[i]*Z)+D1
        if double:
            para[5]*=Stren[i]
            para[4]=lamb2pix(Paschen[i]*Z)+D2
            SynthSpec+=twogauss(para,x=x,returnmodel=True)
        else:
            SynthSpec+=gauss(para,x=x,returnmodel=True)

    if plot:    
        plotspec(SynthSpec)
        plotspec(data)
        plotspec(data-SynthSpec,Z=Z,region='cat',plotlines=False)
    
    return SynthSpec

def createPaschenSul(data,velRange=None,guessV=None,plot=False,plotfit=False,PaNumb=9):

    
    fitresults=findLine(data,velRange=velRange,guessV=guessV,plot=plotfit)
    if fitresults==-1:
        return N.zeros(SpecLen,'Float32')
    else:
        Z,fitpara,D1,D2=fitresults
            
    Pasch=Paschen * Z

    parinfo=[]
    for i in range(7):
        parinfo.append({'value':0.0, 'fixed':0, 'limited':[0,0],'limits':[0.0, 0.0], 'step':0.0})
    parinfo[0]['value']=fitpara[0]
    parinfo[1]['value']=D1
    parinfo[1]['fixed']=1
    parinfo[2]['value']=(max(data)-min(data))/2
    parinfo[3]['value']=fitpara[3]
    parinfo[3]['fixed']=1
    parinfo[4]['value']=D2
    parinfo[4]['fixed']=1
    try:
        relampl=fitpara[5]/fitpara[2]
        parinfo[5]['tied'] = str(relampl)+'*p[2]'
    except ZeroDivisionError:
        parinfo[5]['fixed'] = 1
    

    parinfo[6]['value']=fitpara[6]
    parinfo[6]['fixed']=1

    fitresults=findLine(data,velRange=velRange,guessV=z2vel(Z),restlamb=PaLamb(PaNumb),parinfo=parinfo,plot=plotfit)
    if fitresults==-1:
        return N.zeros(SpecLen,'Float32')
    else:
        Z,paschenparam,D1,D2=fitresults

    # don't subtract continuum
    paschenparam[0]=0.0
    
    x=N.arange(SpecLen)
    SynthSpec=N.zeros(SpecLen,'Float32')

    Stren=PaschStren / PaschStren[19-PaNumb]
    #print Stren
    for i in N.arange(len(Paschen)):
        para=paschenparam.copy()
        para[2]*=Stren[i]
        para[5]*=Stren[i]
        para[1]=lamb2pix(Paschen[i]*Z)+D1
        para[4]=lamb2pix(Paschen[i]*Z)+D2
        SynthSpec+=twogauss(para,x=x,returnmodel=True)

    if plot:    
        plotspec(SynthSpec)
        plotspec(data)
        plotspec(data-SynthSpec,Z=Z,region='cat',plotlines=True)
    
    return SynthSpec

def subtrPaschen(data,velRange=None,guessV=None,PaNumb=9,fromSul=True,double=True):
    origshape=data.getshape()
    if len(data.shape) == 3:
        data.shape=(origshape[0]*origshape[1],origshape[2])

    subtracted=N.zeros(data.shape,'Float32')
    if fromSul:
        for i in N.arange(data.shape[0]):
            subtracted[i,:]=data[i,:]-createPaschenSul(data[i,:],velRange=velRange,guessV=guessV,PaNumb=PaNumb)
    else:
        for i in N.arange(data.shape[0]):
            subtracted[i,:]=data[i,:]-createPaschen(data[i,:],velRange=velRange,guessV=guessV,PaNumb=PaNumb,double=double)
    data.shape=origshape
    subtracted.shape=origshape
    return subtracted

def fxcorrelate(galaxy,star):

    write_fits(galaxy,'/tmp/galaxy.fits')
    write_fits(star,'/tmp/star.fits')

    fxcor('/tmp/galaxy.fits','/tmp/star.fits',output='/tmp/spool')

    #first choose the relevant spectral range
    ## margin=200
##     Left=lamb2pix(CaT[0])-margin
##     Right=lamb2pix(CaT[2])+margin
##     return Left,Right
##     relev_star=star[Left:Right]
##     Left=lamb2pix(CaT[0]*Z)-margin
##     Right=lamb2pix(CaT[2]*Z)+margin
##     relev_galax=galaxy[Left:Right]
##     P.plot(relev_star)
##     P.plot(relev_galax)
    #galax='/tmp/galax.fits'
    #templ='/tmp/templ.fits'
    #write_fits(galaxy,galax)
    #write_fits(template,templ)

#########################
####  FITTING
#########################

def imshow(data,vmin=None,vmax=None):
    if vmin==None: vmin=data.min()
    if vmax==None: vmax=data.max()
    P.imshow(N.transpose(data),vmin=vmin,vmax=vmax,interpolation='nearest',origin='lower')


def skyfit(data,sky,region=skyregion,quiet=True):
    factor=N.zeros(data.shape[0],'Float32')
    region=lamb2pix(region)
    parinfo=[]
    for i in range(2):
        parinfo.append({'value':1.0, 'fixed':0, 'limited':[0,0],'limits':[0.0, 0.0], 'step':0.0})

    for i in N.arange(data.shape[0]):
        sdata=data[i,region[0]:region[1]]
        ssky=sky[region[0]:region[1]]
        #print sdata.shape,ssky.shape
        fa={'data':sdata,'sky':ssky}
        fit=mpfit(skyfunc,functkw=fa,parinfo=parinfo,maxiter=200,quiet=quiet)
        factor[i]=fit.params[1]
    return factor
    

def skyfunc(p, fjac=None, data=None, sky=None, returnmodel=False):
    model= p[0] + (p[1]*sky)
    if returnmodel==True:
        return model
    else:
        status = 0
        return([status, (data-model)])

def gauss(p, fjac=None, x=None, y=None, err=None, returnmodel=False):
    """p0=cont p1=ampl p2=center p3=sigma """
    model = p[0] + (p[2] * N.exp( -1* ((x-p[1])**2) / (2*(p[3]**2)) ) ) 

    #nomin=(x-p[2])**2
    #denom=(p[3]**2) * 2
    #expo=N.exp(-1*nomin/denom)
    #model=expo * p[1]
    #model+=p[0]

    # Non-negative status value means MPFIT should continue, negative means
    # stop the calculation.
    #print p
    #P.plot(model)
    if returnmodel==True:
        return model
    else:
        status = 0
        return([status, (y-model)/err])
 

def twogauss(p, fjac=None, x=None, y=None, err=None, returnmodel=False):
    """p0=cont p1=ampl p2=center p3=sigma """
    model = p[0] + (p[2] * N.exp( -1* ((x-p[1])**2) / (2*(p[3]**2)) ) )  + (p[5] * N.exp( -1* ((x-p[4])**2) / (2*(p[6]**2)) ) )

    #P.plot(model)
    if returnmodel==True:
        return model
    else:
        status = 0
        return([status, (y-model)/err])
 

def fitgauss(data,parinfo=None,prin=False,plot=False,quiet=True):
    if isconstant(data):
        return -1

    data=data.astype('Float64')
    #data-=min(data)
    x=N.arange(len(data),type='Float64')
    #err=N.zeros(len(data))+1
    err=1/N.sqrt(data)
    
    fa = {'x':x, 'y':data, 'err':err}

    if parinfo==None:
        parinfo=[]
        for i in range(4):
            parinfo.append({'value':0.0, 'fixed':0, 'limited':[0,0],'limits':[0.0, 0.0], 'step':0.0})

        parinfo[0]['value']=min(data)
        parinfo[0]['limited']=[1,1]
        parinfo[0]['limits']=[min(data),max(data)]
        parinfo[1]['value']=N.argmax(data)
        parinfo[1]['limited']=[1,1]
        parinfo[1]['limits']=[0.0,len(data)]
        parinfo[2]['value']=(max(data)-min(data))
        parinfo[2]['limited']=[1,1]
        parinfo[2]['limits']=[0.0,max(data)]
        parinfo[3]['value']=len(data)/6.
        parinfo[3]['limited']=[1,1]
        parinfo[3]['limits']=[0.0,len(data)/2.]
        

    #print data,x,err,fa,parinfo
    try:
        fit=mpfit(gauss,functkw=fa,parinfo=parinfo,maxiter=200,quiet=quiet)
    except OverflowError:
        return -1
    
    if plot==True:
        P.plot(data,'r')
        P.plot(gauss(fit.params,x=N.arange(len(data)),returnmodel=True),'b')
    if prin==True:
        print fit.niter,fit.params,fit.status
    
    return fit


def fit2gauss(data,parinfo=None,plot=False,prin=False,quiet=True):
    if isconstant(data):
        return -1

    data=data.astype('Float64')
    #data-=min(data)
    x=N.arange(len(data),type='Float64')
    #err=N.zeros(len(data))+1
    err=1/N.sqrt(data)
    
    fa = {'x':x, 'y':data, 'err':err}

    if parinfo==None:
        parinfo=[]
        for i in range(7):
            parinfo.append({'value':0.0, 'fixed':0, 'limited':[0,0],'limits':[0.0, 0.0], 'step':0.0})

        parinfo[0]['value']=min(data)
        parinfo[0]['limited']=[1,1]
        parinfo[0]['limits']=[min(data),max(data)]
        parinfo[1]['value']=N.argmax(data)
        parinfo[1]['limited']=[1,1]
        parinfo[1]['limits']=[0.0,len(data)]
        parinfo[2]['value']=(max(data)-min(data))
        parinfo[2]['limited']=[1,1]
        parinfo[2]['limits']=[0.0,max(data)]
        parinfo[3]['value']=len(data)/6.
        parinfo[3]['limited']=[1,1]
        parinfo[3]['limits']=[0.0,len(data)/2.]
        parinfo[4]['value']=N.argmax(data)
        parinfo[4]['limited']=[1,1]
        parinfo[4]['limits']=[0.0,len(data)]
        parinfo[5]['value']=0.0
        parinfo[5]['limited']=[1,1]
        parinfo[5]['limits']=[0,max(data)]
        parinfo[6]['value']=len(data)/2.
        parinfo[6]['limited']=[1,1]
        parinfo[6]['limits']=[0.0,len(data)/2.]
    else:
        parinfo[1]['value']+=len(data)/2
        parinfo[4]['value']+=len(data)/2
      

    #print data,x,err,p0,fa,parinfo
    try:
        fit=mpfit(twogauss,functkw=fa,parinfo=parinfo,maxiter=200,quiet=quiet)
    except OverflowError:
        return -1
        
    if plot==True:
        P.plot(data,'r')
        P.plot(twogauss(fit.params,x=N.arange(len(data)),returnmodel=True),'b')
    if prin==True:
        print fit.niter,fit.params,fit.status
    return fit



#########################
####  PLOTTING
#########################

def selective_sum(data,range='cat',Z=1.002912,axis=2):
    if range=='cat': zmin,zmax=lamb2pix(N.array([8470,8700])*Z)
    else: zmin,zmax=0,data.shape[-1]
    print data.shape
    return N.sum(data[:,:,zmin:zmax],axis)
selsum=selective_sum

def selective_average(data,range='cat',Z=1.002912,axis=2):
    if range=='cat': zmin,zmax=lamb2pix(N.array([8470,8700])*Z)
    else: zmin,zmax=0,data.shape[-1]

    if len(data.shape)==3: return N.average(data[:,:,zmin:zmax],axis)
    elif len(data.shape)==1: return N.average(data[zmin:zmax])
selav=selective_average

def showsum(data,vmin=1E5,vmax=2E6,range='cat',Z=1.002912,typ='sum'):
    if typ=='sum': dat=selsum(data,range=range,axis=2)
    elif typ=='aver': dat=selav(data,range=range,axis=2)
    P.imshow(N.transpose(dat),origin='lower',interpolation='nearest',vmin=vmin,vmax=vmax)

def plotspec(data,region=None,plotlines=False,Z=1.002912,style=False,linestyle='steps'):
    
    if style:
        P.plot((N.arange(SpecLen)*Step)+Lamb0,data,style,linestyle=linestyle)
    else:
        P.plot((N.arange(SpecLen)*Step)+Lamb0,data,linestyle=linestyle)

    if plotlines == True:
        CaTz= CaT * Z
        Paschenz=Paschen * Z
        EmissionLinesz=EmissionLines * Z
        for i in N.arange(len(CaTz)): P.plot([CaTz[i],CaTz[i]],P.axis()[2:],'r')
        for i in N.arange(len(Paschenz)): P.plot([Paschenz[i],Paschenz[i]],P.axis()[2:],'k')
        for i in N.arange(len(EmissionLinesz)): P.plot([EmissionLinesz[i],EmissionLinesz[i]],P.axis()[2:],'b')

    if region == 'cat': # legacy
        region=[8470,8700]
    if region != None:
        relevant=data[lamb2pix(region[0]*Z):lamb2pix(region[1]*Z)]
        vmin,vmax=relevant.min(),relevant.max()
        P.axis([region[0]*Z,region[1]*Z,vmin,vmax])
    
    else: pass



#########################
####  IDL Wrappers
#########################

def log_rebin(spec,lamRange):
    """ wrapper for IDL's log_rebin"""

    
    # make a new IDL session
    idl=IDL()

    # give the variables to IDL 
    idl.put('spec',spec)
    idl.put('lamRange',lamRange)

    #construct the IDL command and execute it
    idlcommand='LOG_REBIN, lamRange, spec, specNew, logLam, VELSCALE=velScale'
    idl.eval(idlcommand)
    
    # get the result
    specNew=N.array(idl.get('specNew'))
    logLam=N.array(idl.get('logLam'))

    return specNew,logLam

    
def ppxf():
    """ wrapper for ppxf in IDL"""
    #PPXF, star, galaxy, noise, velScale, start, sol, $
    #;       BESTFIT=bestFit, BIAS=bias, /CLEAN, DEGREE=degree, ERROR=error, $
    #;       GOODPIXELS=goodPixels, MDEGREE=mdegree, MOMENTS=moments, $
    #;       /OVERSAMPLE, /PLOT, /QUIET, VSYST=vsyst, WEIGHTS=weights

    

def voronoi2dbinning(data,Noise=False,targetSN=20,plot=True,quiet=False):
    """ wrapper to do voronoi binning
     CAREFUL: treats 2d-data as two spatial dimensions
    """
    origshape=data.getshape()
    if len(data.shape) == 3 and Noise==False:
        X,Y=getXY(data)
        data.shape=(origshape[0]*origshape[1],origshape[2])
        Signal=S.average(data,axis=1)
        Noise=S.std(data,axis=1)
        data.shape=origshape
    elif len(data.shape) == 3 and Noise!=False:
        X,Y=getXY(data)
        data.shape=(origshape[0]*origshape[1],origshape[2])
        Signal=S.average(data,axis=1)
        Noise=N.resize(Noise,Signal.shape)
        data.shape=origshape
    elif len(data.shape) == 2:
        Signal=N.ravel(data)
        if len(Noise) != len(Signal): Noise=N.resize(Noise,Signal.shape)
        X,Y=getXY(data)
    elif len(data.shape) == 1 and Noise!=False:
        Signal=data
        if len(Noise) != len(Signal): Noise=N.resize(Noise,Signal.shape)
        X,Y=getXY(data)
    else:
        print "must have a noise level for non-spectral data"
        return -1
        
    #print Signal.shape,Noise.shape,X.shape,Y.shape
    print max(Signal),S.average(Noise),X[N.argmax(Signal)],Y[N.argmax(Signal)]
    # make a new IDL session
    idl=IDL()

    # give the variables to IDL 
    idl.put('X',X)
    idl.put('Y',Y)
    idl.put('Signal',Signal)
    idl.put('Noise',Noise)
    idl.put('targetSN',targetSN)

    #construct the IDL command
    idlcommand='VORONOI_2D_BINNING, X, Y, Signal, Noise, targetSN, BinNumber, xBin, yBin, xBar, yBar, SN, nPixels'
    if plot: idlcommand+=', /PLOT'
    if quiet: idlcommand+=', /QUIET'

    # run the command and save the plot
    
    try:
        idl.eval('set_plot,\'ps\'')
        idl.eval(idlcommand)
        idl.eval('device,/close')
    except AttributeError:
        print "something's wrong in running idl"
        return -1
    
    
    
    # collect the output
    BinNumber=N.array(idl.get('BinNumber'))
    xBin=N.array(idl.get('xBin'))
    yBin=N.array(idl.get('yBin'))
    xBar=N.array(idl.get('xBar'))
    yBar=N.array(idl.get('yBar'))
    SN=N.array(idl.get('SN'))
    nPixels=N.array(idl.get('nPixels'))
    
    return BinNumber, xBin, yBin, xBar, yBar, SN, nPixels
    
def average_bins3(data,BinNumber):
    """BinNumber is of length Npix and contains for each pix the bin-number that it belongs to"""
    origshape=data.getshape()
    Nbins=max(BinNumber)+1
    data=N.reshape(data.copy(),(origshape[0]*origshape[1],origshape[2]))

    BinValues=N.zeros((Nbins,origshape[2]),'Float32')
    counter=N.zeros((Nbins,))
    
    for i in N.arange(len(BinNumber)):
        BinValues[BinNumber[i],:] += data[i,:]
        counter[BinNumber[i]] += 1

    for i in N.arange(len(BinNumber)):
        data[i,:]=BinValues[BinNumber[i]] / counter[BinNumber[i]]

    data.shape=origshape
    return data

def average_bins2(data,BinNumber,prin=False):
    """BinNumber is of length Npix and contains for each pix the bin-number that it belongs to"""
    origshape=data.getshape()
    
    data=N.ravel(data.copy())

    BinValues=binvalues(data,BinNumber)
    
    for i in N.arange(len(BinNumber)):
        data[i]=BinValues[BinNumber[i]]

    data.shape=origshape
    return data

def binvalues(data,BinNumber):

    Nbins=max(BinNumber)+1
    counter=N.zeros((Nbins,))
    BinValues=N.zeros(Nbins,'Float32')
    #print Nbins, BinValues.shape,data.shape
    for i in N.arange(len(BinNumber)):
        BinValues[BinNumber[i]] += data[i]
        counter[BinNumber[i]] += 1
    return BinValues / counter



def rad_profile(data,xbin,ybin,xcen,ycen,BinNumber):
    BinValues=binvalues(data,BinNumber)
    diff=N.sqrt(((xbin-xcen)**2)+((ybin-ycen)**2))
    P.plot(diff,BinValues,'x')


#########################
####  HELPER FUNCTIONS
#########################

def getXY(data):
    i=N.indices((data.shape[0],data.shape[1]))
    return N.ravel(i[0]),N.ravel(i[1])

## def getXY_old(data):
##     #t0=time.time()
##     #X=N.sort(N.resize(N.arange(data.shape[0]),data.shape[0]*data.shape[1]))
##     X=N.reshape(N.transpose(N.reshape(N.resize(N.arange(data.shape[0]),data.shape[0]*data.shape[1]),(data.shape[1],data.shape[0]))),(data.shape[0]*data.shape[1]))
##     Y=N.resize(N.arange(data.shape[1]),data.shape[0]*data.shape[1])
##     #print time.time()-t0
##     return X,Y
## def getXY_old2(data):
##     t0=time.time()
##     Y=N.resize(N.arange(data.shape[1]),data.shape[0]*data.shape[1])
##     X=N.array([])
##     for i in N.arange(data.shape[0]):
##         X=N.concatenate((X,N.zeros(data.shape[1])+i))
##     print time.time()-t0
##     return X,Y
## def getXY_old1(data):
##     t0=time.time()
##     X=N.zeros(data.shape[0]*data.shape[1])
##     Y=N.zeros(data.shape[0]*data.shape[1])
##     count=0
##     for x in N.arange(data.shape[0]):
##         for y in N.arange(data.shape[1]):
##            X[count]=x
##            Y[count]=y
##            count+=1
##     print time.time()-t0
##     return X,Y

def dump(data,filename):
    file=open(filename,'w')
    pickle.dump(data,file)
    file.close()

def load(filename):
    file=open(filename,'r')
    data=pickle.load(file)
    file.close()
    return data

def smooth_gauss(data,sigma):
    gauss=Sig.gaussian(10*sigma,sigma)
    return Sig.convolve(data,gauss/N.sum(gauss),mode='same')

def fourier_CC(data,templ):
    return Sig.correlate(fft(data),fft(templ),mode='same')

def combinecubes(cubes,method='median'):
    origshape=cubes[0].getshape()
    bigcube=N.array([])
    for cube in cubes:
        bigcube=N.concatenate((bigcube,N.ravel(cube)))
    bigcube.shape=(len(cubes),N.product(origshape))
    return N.reshape(S.median(bigcube,axis=0),origshape)

def medianspec(data):
    """  """
    if len(data.shape) == 2:
        medi=S.median(data,axis=0)
    elif len(data.shape) == 3:
        medi=N.reshape(data,(data.shape[0]*data.shape[1],data.shape[2]))
        medi=S.median(medi,axis=0)
    else: medi=data

    return medi

def lamb2pix(data):
    if type(data) == type(1) or type(data) == type(1.0): return int(N.around((data-Lamb0)/Step).astype('Int32'))
    else: return N.around((data-Lamb0)/Step).astype('Int32')

def pix2lamb(data):
    return (data*Step)+Lamb0

def pix2vel(data,lamb0):
    return z2vel(((data*Step)+lamb0 )/ lamb0)

def pix2relvel(data,lamb0):
    return data*Step/lamb0*c

def vel2lamb(data,lamb0):
    return vel2z(data) * lamb0

def vel2z(vel):
    return ((vel/c)+1)

def z2vel(z):
    return (z-1)*c

def isconstant(data):
    if S.std(data)==0.0:
        return True
    else:
        return False

def degrade_old(data,factor=4.25):
    oldlen=data.shape[-1]
    newlen=int(N.floor(oldlen/factor))
    degr=N.zeros(newlen,'Float32')
    for i in N.arange(newlen):
        lower=int(N.ceil(i*factor))
        upper=int(N.floor((i+1)*factor))-1
        if i%2==0: split=upper+1
        else: split=lower-1
        degr[i]=N.sum(data[lower:upper+1])+ (data[split]/2.0)
        
    return degr/factor

def degrade(data,factor=4.25,quadratic=False):
    extfactor=1
    while (factor*extfactor)%1 != 0:
        extfactor+=1
    #print extfactor
    oldlen=data.shape[-1]
    newlen=int(N.floor(oldlen/factor))
    ldata=N.resize(data,(extfactor,oldlen))
    ldata=N.transpose(ldata).flat
    degr=N.zeros(newlen,'Float32')
    fac=int(factor*extfactor)
    for i in N.arange(newlen):
        #print len(ldata[i*fac:(i+1)*fac])
        if quadratic:
            degr[i]=N.sqrt(N.sum((ldata[i*fac:(i+1)*fac])**2))/N.sqrt(fac)
        else:
            degr[i]=N.sum(ldata[i*fac:(i+1)*fac])/fac
        
    return degr

def degradeall(data,factor=4.25,quadratic=False):
    origshape=data.getshape()
    if len(data.shape) == 3:
        data.shape=(origshape[0]*origshape[1],origshape[2])

    npix=data.shape[0]
    newlen=int(N.floor(data.shape[-1]/factor))
    degrad=N.zeros((npix,newlen),'Float32')
    for i in N.arange(npix):
        degrad[i]=degrade(data[i,:],factor,quadratic=quadratic)

    #print origshape,data.shape
    data.shape=origshape
    if len(data.shape) == 3: degrad.shape=(origshape[0],origshape[1],newlen)
    return degrad

def sortbins(data,error,wave,start=Lamb0,binwidth=0.85,end=False,log=False):
    origshape=data.getshape()
    if len(data.shape) == 3:
        data.shape=(origshape[0]*origshape[1],origshape[2])
        error.shape=(origshape[0]*origshape[1],origshape[2])
        wave.shape=(origshape[0]*origshape[1],origshape[2])
    if start < wave[:,0].max():
        print "setting start to"+str(wave[:,0].max())
        start=wave[:,0].max()
    if not end: end=wave[:,-1].min()
    if end > wave[:,-1].min():
        print "setting end to"+str(wave[:,-1].min())
        send=wave[:,-1].min()
    leng=int((end-start)/binwidth)
    end=start+(leng*binwidth)
    print start,end,binwidth,leng

    dat=N.zeros((data.shape[0],leng),'Float32')
    err=dat.copy()
    count=dat.copy()
    for i in N.arange(data.shape[0]):
        bins=((wave-start)/binwidth).astype('Int32')
        for j in N.arange(data.shape[1]):
            if (bins[i,j] >= 0) and (bins[i,j] <leng):
                #print i,j,bins.shape,bins[i,j]
                dat[i,bins[i,j]] += data[i,j]
                err[i,bins[i,j]] += error[i,j]
                count[i,bins[i,j]] += 1.0
        #print dat[i,:],count[i,:]
    dat /= count
    err /= count
    err /= N.sqrt(count)
    
    data.shape=origshape
    error.shape=origshape
    wave.shape=origshape
    return dat,err



def PaLamb(number):
    return Paschen[19-number]

def plotbadpix(color='w'):
    
    P.plot([0,1],[0,1],color)
    P.plot([1,2],[0,1],color)
    P.plot([20,21],[0,1],color)
    P.plot([21,22],[0,1],color)
    P.plot([0,1],[13,14],color)
    P.plot([1,2],[13,14],color)
    P.plot([20,21],[13,14],color)
    P.plot([21,22],[13,14],color)
    P.plot([3,4],[4,5],color)
    P.plot([20,21],[8,9],color)
    P.plot([20,21],[9,10],color)
    P.plot([20,21],[10,11],color)
    
    P.plot([0,1],[1,0],color)
    P.plot([1,2],[1,0],color)
    P.plot([20,21],[1,0],color)
    P.plot([21,22],[1,0],color)
    P.plot([0,1],[14,13],color)
    P.plot([1,2],[14,13],color)
    P.plot([20,21],[14,13],color)
    P.plot([21,22],[14,13],color)
    P.plot([3,4],[5,4],color)
    P.plot([20,21],[9,8],color)
    P.plot([20,21],[10,9],color)
    P.plot([20,21],[11,10],color)


#def inspect(data):
#    for i in range(data.shape[0]):
#        for j in range(data.shape[1]):
#            P.clf()
#            title(str(i)+' - '+str(j))
#            plotspec(data[i,j,:])
#            sleep(1)



if __name__ == '__main__':
    demo()
        

def demo():
    print "This file defines some functions. It is not meant to be executed. Import it instead!"
