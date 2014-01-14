import tornado
import tornado.web
import tornado.template
import tornado.websocket
import tornado.escape
import os
from os.path import expanduser
from gmailextract.extractor import GmailImageExtractor

root_dir = os.path.dirname(os.path.abspath(__file__))
attr_dir = os.path.join(expanduser("~"), "Gmail Images")
if not os.path.isdir(attr_dir):
    os.mkdir(attr_dir)

tpl_loader = tornado.template.Loader(os.path.join(root_dir, 'templates'))
simultaneous = 1
state = {}

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.write(tpl_loader.load("main.html").generate(home_dir=attr_dir))

class SocketHandler(tornado.websocket.WebSocketHandler):

    def on_message(self, message):
        msg = tornado.escape.json_decode(message)
        if 'type' not in msg:
            return
        elif msg['type'] == 'connect':
            self._handle_connect(msg)
        elif msg['type'] == 'sync':
            self._handle_sync(msg)
        else:
            return

    def _handle_connect(self, msg):
        state['extractor'] = GmailImageExtractor(attr_dir, msg['email'],
                                                 msg['pass'], limit=0,
                                                 batch=simultaneous,
                                                 replace=False)
        if not state['extractor'].connect():
            self.write_message({'ok': False,
                                "type": "connect",
                                'msg': u"Unable to connect to Gmail with provided credentials"})
        else:
            self.write_message({'ok': True,
                                "type": "connect",
                                "msg": u"Successfully connecting with Gmail."})

            num_messages = state['extractor'].num_messages_with_attachments()
            self.write_message({'ok': True,
                                "type": "count",
                                "msg": u"Found {0} messages with attachments".format(num_messages),
                                "num": num_messages})

            def _status(*args):
                if args[0] == 'message':
                    msg = u"Fetching {0} messages, {1} - {2}".format(simultaneous, args[1], num_messages)
                    self.write_message({"ok": True,
                                        "type": "downloading",
                                        "msg": msg,
                                        "num": args[1]})

            attachment_count = state['extractor'].extract(_status)
            self.write_message({"ok": True,
                                "type": "download-complete",
                                "msg": "Succesfully stored {0} attachments to disk".format(attachment_count),
                                "num": attachment_count})

    def _handle_sync(self, msg):
        extractor = state['extractor']

        self.write_message({"ok": True,
                            "type": "file-checking",
                            "msg": "Checking to see which files have been deleted."})
        num_deletions = extractor.check_deletions()
        self.write_message({"ok": True,
                            "type": "file-checked",
                            "msg": "Found {0} images deleted".format(num_deletions),
                            "num": num_deletions})

        def _sync_status(*args):
            update_type = args[0]
            if update_type == "fetch":
                self.write_message({"ok": True,
                                    "type": "removing",
                                    "msg": u"Removing {0} images from message '{1}'".format(args[2], args[1])})
            elif update_type == "write":
                self.write_message({"ok": True,
                                    "type": "removed",
                                    "msg": "Writing altered version"})

        num_attch_removed, num_msg_changed = extractor.sync(callback=_sync_status)
        self.write_message({"ok": True,
                            "type": "finished",
                            "msg": "Removed {0} images from {1} messages".format(num_attch_removed, num_msg_changed)})

    def on_close(self):
        state['extractor'] = None


if __name__ == "__main__":
    application = tornado.web.Application([
        (r"/assets/(.*)", tornado.web.StaticFileHandler, {"path": os.path.join(root_dir, 'assets')}),
        (r'/ws', SocketHandler),
        (r"/", MainHandler),
    ])
    application.listen(8888)
    tornado.ioloop.IOLoop.instance().start()
