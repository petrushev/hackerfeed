import yaml

from twisted.application.service import Application
from hackerfeed import HNService

config = yaml.load(open('config.yaml'))

application = Application("Hackerfeed")
hnService = HNService(config)
hnService.setServiceParent(application)
