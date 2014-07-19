from string import punctuation
from datetime import date
import json
import dbus

from lxml.html import fromstring

from twisted.application.service import Service
from twisted.internet import reactor
from twisted.python import log

import treq

DBUS_ITEM = "org.freedesktop.Notifications"
DBUS_PATH = "/org/freedesktop/Notifications"
DBUS_INTERFACE = "org.freedesktop.Notifications"

def notify(notifyHandle, title, text):
    """Partial for sending dbus notifications"""
    return notifyHandle.Notify('Hacker News feed', 0, '', title, text, '', '', 3000)

def filterTitle(title, keywords):
    """True if at least one keyword is in title"""
    for p in punctuation:
        title = title.replace(p, ' ')
    title = ' ' + title.lower() + ' '
    for keyword in keywords:
        if keyword in title:
            return True
    return False

def extractLinks(body):
    """Returns a dictionary with url->title mapping"""
    doc = fromstring(body.decode('utf-8'))
    links = doc.cssselect("td.title a[href]")
    links.pop()
    links = dict((title_a.attrib['href'], title_a.text)
                 for title_a in links)
    return links

class HNService(Service):
    """Main service"""

    def __init__(self, config):
        self.setName('Hackerfeed service')
        self.interval = config['interval']
        self.keywords = tuple(' ' + word.strip()
                              for word in config['keywords'].split(','))

    def startService(self):
        # load history from state
        try:
            with open('state', 'r') as f:
                state = json.loads(f.read())
            history = set(state['history'])
        except Exception, exc:
            history = set()
            log.err('Error reading state: ' + str(exc))

        self.history = history

        bus = dbus.SessionBus()
        notifyObj = bus.get_object(DBUS_ITEM, DBUS_PATH)
        self.notifyHandle = dbus.Interface(notifyObj, DBUS_INTERFACE)

        log.msg('HNService started.')

        self.fetch()

    def stopService(self):
        # save history to state
        log.msg('HNService stoping...')
        try:
            state = json.dumps({'history': tuple(self.history)})
            with open('state', 'w') as f:
                f.write(state)
        except Exception, exc:
            log.err('Error writing state: ' + str(exc))

    def fetch(self):
        treq.get('http://news.ycombinator.com/newest')\
            .addCallback(treq.content)\
            .addCallback(self.onResponse)\
            .addErrback(self.onGetError)

    def onGetError(self, failure):
        log.err(failure.getErrorMessage())

        # try again in 30 seconds
        reactor.callLater(30, self.fetch)

    def onResponse(self, responseContent):
        """Called when new content arrives"""
        # schedule next crawl
        reactor.callLater(self.interval, self.fetch)

        links = extractLinks(responseContent)
        new_ = set(links.keys()).difference(self.history)
        self.history.update(new_)

        # send system notifications for new urls
        today = date.today()
        appendLog = ''
        for url in new_:
            title = links[url]
            appendLog = appendLog + ('%s %s : %s\n' % (today.strftime('%Y-%m-%d'), title.encode('utf-8'), url))
            if filterTitle(title, self.keywords):
                self.notifySystem(title, url)

        # update archive
        archiveName = today.strftime('archive-%Y-%m.txt')
        with open(archiveName, 'a') as f:
            f.write(appendLog)

    def notifySystem(self, title, url):
        """Send system notification for a given url"""
        notify(self.notifyHandle,
               title="Hacker News:",
               text="<b>%s</b><br/><br/><span><a href=\"%s\" >%s</a></span>" % (title, url, url))
