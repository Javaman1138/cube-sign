#!/usr/bin/env python
import os, sys, urllib2

import getpass
import logging

import requests
import sleekxmpp
import thread
import time
from datetime import datetime
from optparse import OptionParser
from pyexchange import Exchange2010Service, ExchangeNTLMAuthConnection
from pytz import timezone

STATUS_URL = "http://cubesign.me/{0}/status"
OUTLOOK_URL = "https://agmail.amgreetings.com/EWS/Exchange.asmx"
HIPCHAT_USERNAME_SUFFIX = "@chat.hipchat.com"

#cube sign statuses
STATUS_CUBESIGN_AVAILABLE = "available"
STATUS_CUBESIGN_AWAY = "away"
STATUS_CUBESIGN_OUT = "out"
STATUS_CUBESIGN_WFH = "wfh"
STATUS_CUBESIGN_VACAY = "vacation"
STATUS_CUBESIGN_MEETING = "meeting"
STATUS_CUBESIGN_DND = "dnd"
STATUS_CUBESIGN_OFFICE_HOURS = "office-hours"
STATUS_CUBESIGN_DRAGONS = "dragons"
DEFAULT_STATUS = STATUS_CUBESIGN_AVAILABLE

#hip chat statuses
STATUS_HIPCHAT_DND = "dnd"
STATUS_HIPCHAT_AWAY = "xa"
STATUS_HIPCHAT_IDLE = "away"
STATUS_HIPCHAT_AVAILABLE = "chat"

#outlook subject keys (starts with)
STATUS_OUTLOOK_VACATION = "vacation"
STATUS_OUTLOOK_OOO = "ooo"
STATUS_OUTLOOK_WFH = "wfh"
STATUS_OUTLOOK_OFFICE_HOURS = "office hours"

def setHipChatStatus(status, message):
    print 'hipchatStatus'
    global hipchatStatus
    hipchatStatus = {'status': status, 'message': message}
    print hipchatStatus
    determineStatusPage()

def setOutlookStatus(subject, startTime, endTime, location):
    print 'outlookStatus'
    global outlookStatus
    outlookStatus = {'subject': subject, 'start':startTime, 'end':endTime, 'location':location}
    print outlookStatus
    determineStatusPage()

def clearOutlookStatus():
    print 'clearOutlookStatus'
    global outlookStatus
    outlookStatus = {}
    determineStatusPage()

def determineStatusPage():
    update_status = DEFAULT_STATUS
    update_status_msg = None
    custom = False

    if hipchatStatus and hipchatStatus['status'] == STATUS_HIPCHAT_DND:
        #DND takes recedence
        update_status = STATUS_CUBESIGN_DND
        if USER_ID == 'aschulak':
            update_status = STATUS_CUBESIGN_DRAGONS
        if hipchatStatus['message'] is not None:
            update_status_msg = hipchatStatus['message']
    elif not outlookStatus and hipchatStatus and (hipchatStatus['status'] == STATUS_HIPCHAT_AWAY
                                                or hipchatStatus['status'] == STATUS_HIPCHAT_IDLE):
        #UNothing in outlook, but user is idle or away
        update_status = STATUS_CUBESIGN_AWAY
        if hipchatStatus['message'] is not None:
            update_status_msg = hipchatStatus['message']
    elif outlookStatus:
        if outlookStatus['subject'].lower().startswith(STATUS_OUTLOOK_WFH):
            update_status = STATUS_CUBESIGN_WFH
        elif outlookStatus['subject'].lower().startswith(STATUS_OUTLOOK_OOO):
            update_status = STATUS_CUBESIGN_OUT
        elif outlookStatus['subject'].lower().startswith(STATUS_OUTLOOK_VACATION):
            update_status = STATUS_CUBESIGN_VACAY
        elif outlookStatus['subject'].lower().startswith(STATUS_OUTLOOK_OFFICE_HOURS):
            update_status = STATUS_CUBESIGN_OFFICE_HOURS
        else:
            custom = True
            location = None
            if 'location' in outlookStatus:
                update_status_msg = outlookStatus['location'].split("|")
            updateStatusPageCustom("In a Meeting", update_status_msg)


    if not custom:    
        updateStatusPage(update_status, update_status_msg)

def updateStatusPage(update_status, update_status_msg):
    print 'sending...'
    print "http://" + STATUS_URL + '/status'
    payload = {'status': update_status, 'detail': update_status_msg}
    try:
        r = requests.put(STATUS_URL.format(USER_ID), data=payload)
    except urllib2.HTTPError:
        print r.headers
                
    print r.status_code

def updateStatusPageCustom(primary, detail, css_class='out'):
    print 'sending...'
    print "http://" + STATUS_URL + '/status'
    payload = {
        'class': css_class,
        'primary': primary,
        'detail': detail
    }
    try:
        r = requests.put(STATUS_URL.format(USER_ID), data=payload)
    except urllib2.HTTPError:
        print r.headers
                
    print r.status_code

"""
 * Thread to monitor hip chat status
"""
def hipChatThread(jid, password):
    xmpp = StatusBot(jid, password)

    if xmpp.connect():
        xmpp.process(block=True)
        print("Done")
    else:
        print("Unable to connect.")

class StatusBot(sleekxmpp.ClientXMPP):
    """
    A basic SleekXMPP bot that look for changes in status
    """
    def __init__(self, jid, password):
        sleekxmpp.ClientXMPP.__init__(self, jid, password)

        # The session_start event will be triggered when
        # the bot establishes its connection with the server
        # and the XML streams are ready for use. We want to
        # listen for this event so that we we can initialize
        # our roster.
        self.add_event_handler("session_start", self.start, threaded=True)
        self.add_event_handler('changed_status', self.changed_status)

    def start(self, event):
        self.send_presence()
        self.get_roster()

    def changed_status(self, presence):
        if str(presence['from']).startswith(str(self.requested_jid)):
            status_show = presence._get_sub_text('show')
            status_msg = presence._get_sub_text('status')

            setHipChatStatus(status_show, status_msg)

class XChange(object):

    connection = None
    service = None

    def connect(self, username, password):
        self.connection = ExchangeNTLMAuthConnection(url=OUTLOOK_URL, username=username, password=password)
        self.service = Exchange2010Service(self.connection)

    def get_today_events(self):
        eastern = timezone('US/Eastern')
        now = eastern.localize(datetime.now())
        check_time = datetime(year=now.year, month=now.month, day=now.day, hour=now.hour, minute=now.minute, second=0)
        estart = datetime(year=now.year, month=now.month, day=now.day, hour=0, minute=0, second=0)
        estop = datetime(year=now.year, month=now.month, day=now.day, hour=23, minute=59, second=59)

        clearOutlookStatus()

        cal = self.service.calendar()
        events = cal.list_events(start=estart, end=estop, details=True)
        events.load_all_details()
        print 'there are {0} events today.'.format(len(events.events))
        for event in events.events:
            meeting_start = event.start.astimezone(eastern)
            meeting_end = event.end.astimezone(eastern)
            if (now >= meeting_start) and (now <= meeting_end):
                setOutlookStatus(event.subject, event.start, event.end, event.location)


if __name__ == '__main__':
    hipchatStatus = {}
    outlookStatus = {}

    # Setup the command line arguments.
    optp = OptionParser()

    # Output verbosity options.
    optp.add_option('-q', '--quiet', help='set logging to ERROR',
                    action='store_const', dest='loglevel',
                    const=logging.ERROR, default=logging.INFO)
    optp.add_option('-d', '--debug', help='set logging to DEBUG',
                    action='store_const', dest='loglevel',
                    const=logging.DEBUG, default=logging.INFO)
    optp.add_option('-v', '--verbose', help='set logging to COMM',
                    action='store_const', dest='loglevel',
                    const=5, default=logging.INFO)

    # JID and password options.
    optp.add_option("-j", "--jid", dest="jid",
                    help="hipchat JID to use")
    optp.add_option("-p", "--password", dest="password",
                    help="hipchat password to use")
    # Email and password options.
    optp.add_option("-e", "--email", dest="email",
                    help="email address")
    optp.add_option("-x", "--xpassword", dest="email_password",
                    help="email password")
    opts, args = optp.parse_args()

    # Setup logging.
    logging.basicConfig(level=opts.loglevel,
                        format='%(levelname)-8s %(message)s')

    if opts.jid is None:
        opts.jid = raw_input("Hip Chat JID: ")
    if opts.password is None:
        opts.password = getpass.getpass("Hip Chat Password: ")
    if opts.email is None:
        opts.email = raw_input("Email Address: ")
    if opts.email_password is None:
        opts.email_password = getpass.getpass("Email Password: ")

    global USER_ID
    USER_ID = opts.email.split('@')[0]

    #Start the hp chat monitor thread
    if opts.jid and opts.password:
        if len(opts.jid.split('@')) == 1:
            opts.jid = opts.jid + HIPCHAT_USERNAME_SUFFIX
        thread.start_new_thread(hipChatThread, (opts.jid, opts.password))

    outlookMonitor = XChange()
    try:
        while True:
            if opts.email and opts.email_password:
                print 'checking outlook...'
                outlookUser = "USAG\\" + USER_ID
                outlookMonitor.connect(outlookUser, opts.email_password)
                outlookMonitor.get_today_events()
                time.sleep(300)
    except (KeyboardInterrupt, SystemExit):
        print 'interrupted'
        os._exit(1)
    except:
        print 'other exception'
        sys.exit(0)

    print 'Program Ended'


