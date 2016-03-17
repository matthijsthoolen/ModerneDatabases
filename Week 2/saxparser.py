import xml.sax
from yamr import Database, Chunk, Tree
from server import *


class NVDHandler(xml.sax.ContentHandler):

    def __init__(self):
        self.CurrentData = ""
        self.db = getDb('nvd.db')
        self.id = ""
        self.products = []

    # Call when an element starts
    def startElement(self, tag, attributes):
        self.CurrentData = tag
        if tag == "entry":
            print("*****Entry*****")
            self.id = attributes["id"]
            print("ID:", self.id)

    # Call when an elements ends
    def endElement(self, tag):
        if tag == "entry":
            print("hoi")
            self.db[self.id] = self.products
            self.products = []
        elif tag == "nvd":
            print("committing")
            self.db.commit()
            CloseDb(self.db)

        self.CurrentData = ""

    # Call when a character is read
    def characters(self, content):
        if self.CurrentData == "vuln:product":
            self.products += [content]

if (__name__ == "__main__"):
    # create an XMLReader
    parser = xml.sax.make_parser()
    # turn off namepsaces
    parser.setFeature(xml.sax.handler.feature_namespaces, 0)

    # override the default ContextHandler
    Handler = NVDHandler()
    parser.setContentHandler(Handler)
    parser.parse("Database files/test.xml")
