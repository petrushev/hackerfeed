from string import punctuation
from datetime import date
import json

from lxml.html import fromstring

from twisted.application.service import Service
from twisted.internet import reactor
from twisted.python import log

import treq
from txdbus.client import connect as dbusConnect

DBUS_ITEM = "org.freedesktop.Notifications"
DBUS_PATH = "/org/freedesktop/Notifications"
NOTIFY_CMD = 'Notify'

MESSAGE_TPL = u"""<b>{0}</b><br/><br/><span><a href="{1}" >{1}</a></span>"""


def notify(notifier, title, text):
    """Partial for sending dbus notifications"""
    d = notifier.callRemote(NOTIFY_CMD, 'Hacker News feed', 0, '',
                            title, text,
                            [], {}, 3000)
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

        # connect to dbus
        dbusConnect(reactor, 'session')\
            .addCallback(self.onDbusConnect)

    def onDbusConnect(self, connection):
        self.dbusConnection = connection

        # get notifier
        connection.getRemoteObject(DBUS_ITEM, DBUS_PATH)\
                  .addCallback(self.onNotifierReady)

    def onNotifierReady(self, notifier):
        self.notifier = notifier

        # start first fetch
        self.fetch()

    def stopService(self):
        log.msg('HNService stoping...')

        # save history to state
        try:
            state = json.dumps({'history': tuple(self.history)})
            with open('state', 'w') as f:
                f.write(state)
        except Exception, exc:
            log.err('Error writing state: ' + str(exc))

        # close dbus connection
        self.dbusConnection.disconnect()

    def fetch(self):
        url = 'http://news.ycombinator.com/newest'
        d = treq.get(url)\
                .addCallback(treq.content)\
                .addErrback(self.onGetError)
        d = d.addCallback(self.onResponse, url)\
             .addErrback(self.onParseError)

    def onGetError(self, failure):
        log.err('Fetch error: ' + failure.getErrorMessage())
        # try again in 30 seconds
        reactor.callLater(30, self.fetch)

    def onParseError(self, failure):
        log.err('Parse error: ' + failure.getErrorMessage())
        # try again in 30 seconds
        reactor.callLater(30, self.fetch)

    def onResponse(self, responseContent, url):
        """Called when new content arrives"""

        links = extractLinks(responseContent, url)
        new_ = set(links.keys()).difference(self.history)
        self.history.update(new_)

        # send system notifications for new urls
        today = date.today()
        appendLog = ''

        for url in new_:
            title = links[url]
            title_enc = title.encode('utf-8', 'replace')
            msg = '{0} {1} : {2}\n'.format(today.strftime('%Y-%m-%d'), title_enc, url)
            appendLog = appendLog + msg

            if filterTitle(title, self.keywords) or filterUrl(url, self.domains):
                notify(self.notifier,
                       title="Hacker News:",
                       text= MESSAGE_TPL.format(title, url, url))

        # update archive
        archiveName = today.strftime('archive-%Y-%m.txt')
        with open(archiveName, 'a') as f:
            f.write(appendLog)

        # schedule next crawl
        reactor.callLater(self.interval, self.fetch)
