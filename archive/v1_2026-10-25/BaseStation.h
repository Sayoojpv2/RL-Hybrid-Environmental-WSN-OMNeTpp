#ifndef __PERIYAR_BASESTATION_H
#define __PERIYAR_BASESTATION_H

#include <omnetpp.h>
using namespace omnetpp;

class Controller;

/** Sink at (600, 25) m, mains powered (MATLAB index n+1 = 51). */
class BaseStation : public cSimpleModule
{
  protected:
    Controller *ctl = nullptr;
    long deliveredReports = 0, framesReceived = 0, framesLost = 0;
    simsignal_t delaySignal, latencySignal, hopsSignal;
    virtual int numInitStages() const override { return 2; }
    virtual void initialize(int stage) override;
    virtual void handleMessage(cMessage *msg) override;
    virtual void refreshDisplay() const override;
    virtual void finish() override;
  public:
    long delivered() const { return deliveredReports; }
};

#endif
