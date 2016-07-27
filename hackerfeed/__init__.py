from string import punctuation
from datetime import date
import json

from lxml.html import fromstring

from twisted.application.service import Service
from twisted.internet import reactor
from twisted.python import log

import treq
from txdbus.client import connect as dbusConnect
from twisted.web._newclient import ResponseNeverReceived
from twisted.internet.error import ConnectingCancelledError
from twisted.internet.defer import gatherResults, Deferred
from twisted.internet.task import deferLater

DBUS_ITEM = "org.freedesktop.Notifications"
DBUS_PATH = "/org/freedesktop/Notifications"
NOTIFY_CMD = 'Notify'

MESSAGE_TPL = u"""<b>{0}</b><br/><br/><span><a href="{1}" >{1}</a></span>"""


def onNotifierReady(notifier, messages):
    """Given notifier, dispatch all messages"""
    deferreds = []
    for text in messages:
        single = notifier.callRemote(
            NOTIFY_CMD, 'Hacker News feed', 0, '', "Hacker News:", text, [], {}, 6000)
        deferreds.append(single)
    del single

    return gatherResults(deferreds, consumeErrors=True)

def onDbusConnect(connection, messages):
    d = Deferred()
    internal = connection.getRemoteObject(DBUS_ITEM, DBUS_PATH)

    internal.addCallback(onNotifierReady, messages)
    internal.addErrback(d.errback)

    def noficationDone(code):
        connection.disconnect()
        d.callback(code)

    internal.addCallback(noficationDone)
    internal.addErrback(d.errback)

    return d

def notify(messages):
    d = dbusConnect(reactor, 'session')
    d.addCallback(onDbusConnect, messages)
    return d


def filterTitle(title, keywords):
    """True if at least one keyword is in title"""
    for p in punctuation:
        title = title.replace(p, ' ')
    title = ' ' + title.lower() + ' '
    for keyword in keywords:
        if keyword in title:
            return True
    return False

def filterUrl(url, domains):
    for domain in domains:
        if domain in url:
            return True
    return False

def extractLinks(body, url):
    """Returns a dictionary with url->title mapping"""
    doc = fromstring(body.decode('utf-8'))
    doc.make_links_absolute(url)
    links = doc.cssselect("td.title > a[href]")
    links.pop()
    links = dict((title_a.attrib['href'], title_a.text_content())
                 for title_a in links)
    return links


class HNService(Service):
    """Main service"""

    def __init__(self, config):
        self.setName('Hackerfeed service')
        self.interval = config['interval']
        self.keywords = tuple(' ' + word.strip()
                              for word in config['keywords'].split(','))
        self.domains = tuple(domain.strip()
                             for domain in config['domains'].split(','))

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

        reactor.callWhenRunning(self.fetch)

    def stopService(self):
        log.msg('HNService stoping...')

        # save history to state
        try:
            state = json.dumps({'history': tuple(self.history)})
            with open('state', 'w') as f:
                f.write(state)
        except Exception, exc:
            log.err('Error writing state: ' + str(exc))

    def fetch(self):
        url = 'http://news.ycombinator.com/newest'
        treq.get(url, timeout=10)\
            .addCallback(treq.content)\
            .addCallback(self.onResponse, url)\
            .addErrback(self.onResponseError)

    def onResponseError(self, failure):
        msg = 'Fetch / parse error: '
        if failure.type in (ConnectingCancelledError, ResponseNeverReceived):
            msg = msg + 'connection timeout!'
        elif failure.type == UnicodeEncodeError:
            msg = failure.getTraceback()
        else:
            msg = msg + '{0}, {1}'.format(repr(failure.type), failure.getErrorMessage())
        log.msg(msg)

        # try again in 30 seconds
        deferLater(reactor, 30, self.fetch)

    def onResponse(self, responseContent, url):
        """Called when new content arrives"""

        links = extractLinks(responseContent, url)
        new_ = set(links.keys()).difference(self.history)
        self.history.update(new_)

        # send system notifications for new urls
        today = date.today()
        appendLog = ''

        messages = []

        for url in new_:
            title = links[url]
            title_enc = title.encode('utf-8', 'replace')
            msg = '{0} {1} : {2}\n'.format(today.strftime('%Y-%m-%d'), title_enc, url)
            appendLog = appendLog + msg

            if filterTitle(title, self.keywords) or filterUrl(url, self.domains):
                messages.append(MESSAGE_TPL.format(title, url, url))

        notify(messages)

        # update archive
        archiveName = today.strftime('archive-%Y-%m.txt')
        with open(archiveName, 'a') as f:
            f.write(appendLog)

        # schedule next crawl
        deferLater(reactor, self.interval, self.fetch)
